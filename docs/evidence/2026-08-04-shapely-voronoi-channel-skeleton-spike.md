<!-- provenance: commit=15110feccc6ec9389f0777d3cff1ce9f81b11068 dirty=true (branched from origin/main at 15110fecc; the only working-tree deltas at measurement time were this document and the untracked harness tools/measurements/voronoi_channel_skeleton_spike.py. No production file was modified — channel_skeleton.py was measured exactly as it stands on main.) -->

# S4 spike: shapely/GEOS Voronoi in `router_v6/channel_skeleton.py` (2026-08-04)

**Verdict: NARROW THE SEAM. The recorded gate — "spike-gated on the shapely
Voronoi boundary" — tests the wrong boundary.** GEOS's Voronoi is not the
obstacle. An independent, non-GEOS Voronoi reproduces the skeleton graph
*exactly* (isomorphic, identical node and edge counts) with node coordinates
agreeing to better than 1e-9 mm on 12/12 boards. What fails gate G2's
bit-exact `==` bar is not the geometry — it is that the skeleton's downstream
identity is built from **unnormalised raw float coordinates plus networkx
edge-insertion order**. That is a property of `constraint_model.py`, fixable
in Python, and it blocks *any* reimplementation equally — including a
hypothetical bit-exact one.

Secondary verdict, for the ledger: **the gate was recorded but never run.**
See §1.

---

## 1. The gate was recorded, never executed

The gate traces to the Wave 3 roadmap, `docs/plans/2026-07-31-001-feat-wave3-rust-migration-roadmap-plan.md:114`:

> Q5. `channel_skeleton.py`: whether the Voronoi dependency moves to a Rust
> geometry library or stays shapely with Python orchestration — the edt-crate
> spike (parent KTD8) shows third-party geometry libraries diverge, so this
> needs its own spike before any commitment.

It was carried forward three times without ever being discharged:

| Carrier | Location | What it says |
|---|---|---|
| Wave 3 roadmap | `docs/plans/2026-07-31-001-...-plan.md:70,114` | "needs its own spike before any commitment" |
| Wave 4 program plan | `docs/plans/2026-08-01-001-...-plan.md:19,33,158,190` | "spike-gated per Wave 3 Q5"; "pre-spiked per the Wave 3 Q5 / KTD8 precedent" |
| Verdict ledger | `docs/wave4-verdicts.yaml:146-147` | "channel_skeleton is Phase 4 and spike-gated on the shapely Voronoi boundary" |
| Migration survey | `docs/evidence/2026-08-04-router-v6-migration-survey.md` §2.3 | carried forward as BLOCKED |

Searches performed to confirm no spike was ever run:

- `grep -ril voronoi docs/` — 10 hits, all plans/architecture/ledger prose. No evidence artifact.
- `ls docs/evidence/ | grep -i spike` — three spike documents exist (`2026-07-31-edt-crate-ktd8-spike-rejected.md`, `2026-07-31-ktd9-faer-vs-scipy-spike.md`, `2026-08-01-ortools-cpsat-spike.md`). None concerns Voronoi.
- `git log --all --diff-filter=A --name-only -- docs/evidence/ | grep -iE 'voronoi|skelet|shapely'` — **empty**. No such evidence file has ever existed on any branch, so it was not written and later deleted.
- `gh pr list --state all --search voronoi` — PR #741 (this survey) and PR #732 (`constraints_geometry`, unrelated). No spike PR.
- `git log --all --grep=voronoi -i` — four commits, all feature work on router_v6, none a spike.

**The gate was a ledger entry standing in for a decision nobody made.** Note
the wording drift as it propagated: Wave 3 said the spike was *needed*; the
Wave 4 program plan at line 158 describes channel_skeleton as
"**pre-spiked** per the Wave 3 Q5 / KTD8 precedent". Nothing was pre-spiked.
An unrun gate acquired the language of a discharged one purely by being
restated. **Recommendation: audit the other gates in
`docs/wave4-verdicts.yaml` for the same condition** — a recorded blocker whose
evidence artifact does not exist. This one survived three restatements and a
survey.

---

## 2. Falsifiers, stated before measurement

Declared in the harness docstring
(`tools/measurements/voronoi_channel_skeleton_spike.py`) before any number was
taken, per the convention in `docs/evidence/2026-07-27-first-route-and-profile.md`.

| # | Falsifier | Fired? |
|---|---|---|
| **F1** | GEOS `voronoi_diagram` is bit-identical across repeated calls with the same input in the same process. FIRES if any repeat differs. | **No** |
| **F2** | The GEOS Voronoi *edge set* is invariant to permutation of the input point order. FIRES if a permutation changes the edge set. | **No** |
| **F3** | The GEOS Voronoi *edge sequence* is invariant to permutation of input order. FIRES if ordering changes. | **No** |
| **F4** | The downstream contract is graph topology only, so a permuted-but-valid Voronoi yields an equivalent skeleton for the consumer. | **No** (vacuously — F2/F3 held, so no permuted-but-different Voronoi could be produced to test it. Answered instead by §5.) |

**No falsifier fired.** The expected finding — an order-sensitive GEOS
producing a latent determinism bug in the current Python, in the spirit of
PR #730 ("make component placement independent of PYTHONHASHSEED") — did not
materialise. The prediction was wrong, and §3 explains why.

Environment: Python 3.12.12, shapely 2.1.2, GEOS 3.13.1, darwin/arm64.

Input geometry: `box(0,0,40,30)` minus 6–13 axis-aligned pad rectangles,
which is exactly how the real input is built —
`routing_space.py:95`, `available_area = board_polygon.difference(obstacles)`.
Boundary sampling replicates `channel_skeleton.py:248-269` (~1 mm spacing),
yielding 193–248 Voronoi sites per board. This geometry is deliberately
*degenerate*: axis-aligned rectangles sampled on a uniform pitch produce large
sets of collinear and cocircular sites, the configurations where Voronoi
implementations are most free to disagree.

The harness loads `_extract_medial_axis_single` and
`_ensure_skeleton_connectivity` from the production module file rather than
reimplementing them, so the measurement cannot drift from production. Sibling
imports are stubbed because the compiled `temper_design_bundle_python` in this
checkout is stale relative to the Python source and this spike is forbidden to
build any Rust crate; the stubs raise on access, and none was reached
(`pcb=None` disables the sole `pin_world_position` call site).

---

## 3. Q1 — GEOS Voronoi is deterministic, including under permutation

| Probe | Result |
|---|---|
| 20 repeated calls, same process, same input | 1 distinct digest of 494 edges |
| 3 fresh processes, `PYTHONHASHSEED` ∈ {1, 8, 15} | 1 distinct digest — cross-process stable |
| 8 random permutations of the 215 input sites | edge **set** unchanged (symmetric difference 0), edge **sequence** unchanged (0/8 differ) |

Permutation-invariance is structural, not luck. GEOS canonicalises its input
before triangulating: JTS's `DelaunayTriangulationBuilder` (which
`VoronoiDiagramBuilder` delegates to, and which GEOS ports) sorts the site
coordinates and removes repeats before incremental insertion. A direct probe
on a maximally degenerate set — the unit square's four cocircular corners plus
its centre plus three outer sites, where an order-sensitive implementation has
genuine freedom to differ:

| Variation | Digest matches base? |
|---|---|
| reversed input | **yes** |
| shuffled input | **yes** |
| three duplicate sites appended | **yes** |

**Finding: there is no latent determinism issue here.** The concern that
motivated ordering this question first — that the current Python might carry a
hidden order-sensitivity independent of any migration — is measured and
refuted. `channel_skeleton.py` is order-stable, hash-seed-stable, and
process-stable on this input class. This is a *positive* result for the
existing Python and removes one hazard from any future port: the port need not
reproduce an input ordering, only a canonicalisation.

Scope limit: measured on 2-D point Voronoi over PCB-like sampled boundaries,
GEOS 3.13.1, single platform. Cross-platform and cross-GEOS-version stability
is **UNKNOWN** — not measured, and it would matter for a CI gate.

---

## 4. Q2 — the observable contract is coordinates *and* emission order, not topology

The consumer chain is `channel_skeleton` → `constraint_model.py` →
SAT. The binding site is `constraint_model.py:325-337`
(`_create_per_net_channel_vars`, and identically at 358 and 377 in the bundled
path):

```python
for i, (u, v) in enumerate(skeleton.graph.edges):
    n1, n2 = sorted([u, v])
    edge_id = f"{layer_name}_E{i}_{n1}_{n2}"
    var = NetChannelVar(name=f"uses_N{net_idx}_{edge_id}", ...)
```

Two things become part of the SAT model's identity:

1. **`i`** — the positional index in networkx edge-iteration order, which for
   `nx.Graph` is insertion order, which is the order Voronoi edges came back
   from GEOS and survived the `prepped_buffered.contains(midpoint)` filter.
2. **`n1`, `n2`** — the *raw float tuples*, interpolated with `repr()`. A
   node's identity is its exact IEEE-754 double pair. There is no quantisation
   anywhere: `channel_skeleton.py:104` does `G.add_node(p1, pos=p1)` with `p1`
   straight off `line.coords`.

So the answer to "is the contract topology or coordinates" is: **neither, and
worse than both — it is coordinates plus emission order.** Two skeletons that
are geometrically indistinguishable and graph-isomorphic still produce
disjoint SAT variable-name sets.

How brittle: perturbing the *input sites* by one ULP in x changes **290 of
281** consumer identifiers (all of them, and the edge count shifts 281 → 290).
Not one identifier survives a perturbation nine orders of magnitude below a
manufacturing tolerance.

(`_ensure_skeleton_connectivity` is not the fragile part — its bridge search
is an exhaustive nearest-pair over components and is order-independent given
the same node set.)

---

## 5. Q3/Q4 — the decisive measurement: an independent Voronoi reproduces the skeleton

The question the gate should have asked is not "can Rust reproduce GEOS's
diagram bit-for-bit" but "does a *different correct* Voronoi produce a
different *skeleton*". Measured directly, without building anything, by
substituting **Qhull** (`scipy.spatial.Voronoi`, scipy 1.18.0) for GEOS and
running the identical downstream pipeline — same interior filter, same
simplify, same graph build, same connectivity pass. Qhull is a legitimate
stand-in for a Rust-side Voronoi (`voronator`, `spade`, `geo`): an
independent, mature, non-GEOS implementation of the same object, with a
different construction and different degeneracy handling.

Sweep over 12 boards (193–248 sites, 204–307 skeleton nodes):

| Property | Boards passing |
|---|---|
| Identical node count | **12 / 12** |
| Identical edge count | **12 / 12** |
| Graphs isomorphic (`nx.is_isomorphic`) | **12 / 12** |
| Node sets identical when rounded to 9 dp | **12 / 12** (worst symmetric difference: **0**) |
| Node sets identical at exact float equality | **0 / 12** (worst symmetric difference: 182) |
| Consumer `edge_id` lists identical | **0 / 12** |

Worst-case relative delta in `total_length` across all 12 boards:
**1.05e-15** (absolute delta on the reference board: 1.7e-13 mm).

Read that table carefully, because it is the whole finding:

- **The geometry agrees.** Two independent implementations, on deliberately
  degenerate input, produce skeletons that are isomorphic with identical node
  and edge counts, node positions agreeing to under 1e-9 mm — roughly a
  picometre, about nine orders of magnitude below any PCB tolerance and six
  below KiCad's 1 nm internal unit — and total channel length agreeing to
  within one part in 1e15.
- **The identifiers do not.** Zero of twelve boards produce matching consumer
  `edge_id`s. On the reference board the divergence is at index 0:
  GEOS yields `F.Cu_E0_(0.5, 0.5)_(1.5, 1.5)`, Qhull yields
  `F.Cu_E0_(30.52149924880154, 15.621207949331984)_(31.52149924880154, 16.105686849099794)`.
  That first divergence is *ordering*, not position — both edges exist in both
  skeletons; they are emitted in a different sequence.

**The named concrete failure, precisely:** an independent Voronoi that is
correct to 1e-9 mm changes 100% of the SAT channel-variable names, because
`edge_id` embeds an emission index and an unrounded float `repr`. G2's
bit-exact `==` therefore fails for reasons that have nothing to do with the
Voronoi being hard to reproduce.

This is the opposite of the KTD8 precedent it was filed under. KTD8 rejected
the `edt` crate because the crate computed a **different distance field** —
max divergence 2.0, a real mathematical disagreement. Here the mathematics
agrees to 1e-15 relative and the *contract* disagrees. Reasoning from the KTD8
analogy is what produced a gate aimed at the wrong seam.

Caveats, stated honestly:

- GEOS clips infinite ridges to an envelope; the Qhull path drops them. Node
  counts matched 12/12 regardless, so this did not perturb the comparison
  here, but on geometries where more of the skeleton reaches the outer
  boundary it could. Not exhaustively characterised.
- Synthetic boards, not a real `.kicad_pcb`. The generator mirrors
  `routing_space.py`'s construction exactly, and the input class is
  deliberately the degenerate one, but a real-board replication is **not
  done**.
- Qhull is not `voronator`/`spade`/`geo`. It evidences that *an* independent
  implementation agrees to 1e-9 mm; it does not certify any specific Rust
  crate.

---

## 6. Q3 — does a narrowing exist?

Yes, and it is the highest-value outcome available. **The Voronoi need not be
the interface, and the fix is not in Rust.**

The skeleton contract can be made implementation-independent inside Python,
before any migration, by normalising the two artifacts that carry
implementation identity:

1. **Quantise node coordinates** at graph-build time (`channel_skeleton.py:104-113`)
   to a fixed grid — 1e-6 mm (1 nm, KiCad's native internal unit) is six
   orders coarser than the measured 1e-9 mm cross-implementation agreement and
   still three orders finer than any DRC dimension.
2. **Order edges canonically** — sort by the (quantised) endpoint pair rather
   than letting `E{i}` inherit GEOS's emission order, either in
   `channel_skeleton` or at the `constraint_model.py:329` consumption site.

With those two changes, the §5 sweep's bottom two rows flip from 0/12 to
12/12, and gate G2's bit-exact `==` becomes *satisfiable by any correct
Voronoi* — GEOS, Qhull, `voronator`, or `spade` — rather than only by a
byte-for-byte GEOS clone.

**Does this merely move the parity problem?** Partly, and the honest accounting
is:

- It does **not** move it, in the sense that the current contract is
  unsatisfiable by construction for any reimplementation, and after
  normalisation it is satisfiable by a broad class. That is a real reduction
  in the parity bar, not a relocation.
- It **does** move it, in the sense that quantisation is itself a
  behaviour-changing edit to production Python: every SAT variable name
  changes on the first run, so route selection can change. It needs its own
  A/B under the `TEMPER_*_BACKEND` dispatch precedent (Wave 1), measured on
  real boards, and it is a Python change that must land and be proven
  *before* the Rust question is reopened.
- It leaves untouched the question of whether GEOS and a Rust Voronoi agree
  *topologically* on inputs harder than the ones measured here — the 12/12
  isomorphism result is strong but is 12 synthetic boards, not a proof.

---

## 7. Q4 — Rust crate survey

**Not reached, deliberately.** Questions 1–3 settle the matter: the binding
constraint is a Python-side contract, so surveying `voronator` / `spade` /
`geo` now would evidence the wrong decision. Recorded for whoever reopens it —
the parity evidence a future spike would need, in order:

1. Normalisation (§6) landed and A/B-proven on real boards. Until then, no
   crate can pass, so no crate is worth measuring.
2. Topological parity on **real** `.kicad_pcb` routing areas, not synthetic —
   node count, edge count, isomorphism, quantised node-set equality — at the
   scale the 12-board synthetic sweep only gestures at.
3. Cross-platform and cross-GEOS-version stability of the *current Python*,
   which is presently **UNKNOWN** (§3) and is a prerequisite for any CI gate,
   migration or not.
4. Degenerate-input behaviour specifically: collinear runs and cocircular
   quadruples are the norm on axis-aligned PCB geometry, and are where
   implementations are licensed to differ. GEOS's sort-and-dedup
   canonicalisation (§3) is a behaviour a Rust crate must be confirmed to
   share, not assumed to.

---

## 8. Incidental findings

- **`simplify_tolerance` is dead code on the Voronoi path.** GEOS
  `voronoi_diagram(..., edges=True)` returns exclusively 2-point LineStrings
  (measured: 494/494 segments have 2 coordinates), and Douglas–Peucker on a
  2-point line is the identity. Running `_extract_medial_axis_single` with
  `simplify_tolerance=50.0` instead of the default `0.5` returns a
  byte-identical result. The parameter is documented as a real knob
  (`channel_skeleton.py:53,66`) and
  `docs/evidence/2026-07-27-stage3-model-and-rewrite.md:211` attributes
  skeleton density to it. It has no effect. Only the fallback path could ever
  be affected, and that path does not call `simplify` either.
- **`channel_skeleton.py:113-114` adds the same edge twice** — two identical
  `G.add_edge(p1, p2, weight=length)` calls. Harmless for `nx.Graph`
  (idempotent), and `total_length` is incremented once, so it is redundancy
  rather than a bug.
- **`channel_skeleton.py:133,134-136` compute and discard values** —
  `math.radians(rotation_deg)` and the `comp.initial_side` conditional are
  evaluated as bare expressions with no assignment. Dead statements in the
  pad-anchoring block.

None of these were changed — this is a spike.

---

## 9. Ledger recommendations (not applied)

`docs/wave4-verdicts.yaml` was **not edited**, per the spike's constraints.
Recommended, for whoever owns the ledger:

1. Restate the `router_v6/**` note at `docs/wave4-verdicts.yaml:145-147`:
   channel_skeleton is **not** gated on the shapely Voronoi boundary. It is
   gated on the skeleton contract normalisation (§6), which is Python work.
2. Correct `docs/plans/2026-08-01-001-...-plan.md:158`, which calls
   channel_skeleton "pre-spiked". It was not, until this document.
3. Audit remaining gates for recorded-but-never-run status (§1).
4. The KTD8 analogy at `docs/plans/2026-08-01-001-...-plan.md:190` should be
   dropped for this module — measured, it does not hold (§5).

## 10. Reproduction

```
python3 tools/measurements/voronoi_channel_skeleton_spike.py
```

Requires shapely 2.1.2 (GEOS 3.13.1), scipy 1.18.0, networkx. No Rust crate
is built, imported, or required. Statements moved to Rust: **0** — this is a
spike, and no production file was modified.
