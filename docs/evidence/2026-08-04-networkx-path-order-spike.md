<!-- provenance: commit=15110feccc6ec9389f0777d3cff1ce9f81b11068 dirty=false -->

# Spike S3: is `nx.shortest_path` a real blocker for `router_v6/channel_mapping.py`?

**Date:** 2026-08-04
**Surface:** `packages/temper-placer/src/temper_placer/router_v6/channel_mapping.py`
(203 `ast.stmt`, 178 executable), listed BLOCKED on `networkx` in
`docs/evidence/2026-08-04-router-v6-migration-survey.md` §2.3 (PR #741).
**Scope:** a verdict plus its measurements. **No production code was changed,
no Rust was written, and no Rust crate was built.**

---

## Verdict

**UNBLOCKED — `channel_mapping.py` moves BLOCKED → PORT (203 stmts / 178
exec), but for a reason that must be recorded precisely, because the obvious
short summary of it is wrong.**

The blocker is *not* dissolved by `nx.shortest_path` being order-stable. It is
emphatically **not** order-stable here: on the production board's own channel
skeleton the queried endpoint pair has **256 distinct tied shortest paths**,
and **32 of 32** permutations of graph-construction order return a *different*
path. Had this code been live, the survey's classification would have been
correct and the verdict would be BLOCKED.

The blocker is dissolved because **both `nx.shortest_path` call sites are
unreachable dead code.** They sit inside `_extract_waypoints`'s
`if not channel_sequence:` branch; `_extract_waypoints` has exactly one call
site in the repository; and that call site is dominated by
`if not channel_sequence: return None` four statements earlier. The branch
cannot be entered.

The consequence is that the recommended disposition is **delete, do not
port**. Porting the branch would mean reproducing networkx's bidirectional-BFS
tie-breaking bit-exactly against gate G2's `==` — and §4 shows that is not a
stable target even *within* Python, let alone across a language boundary.
Deleting it removes `networkx` from `channel_mapping.py` **entirely**
(measured: the only `nx` references in the file are lines 339, 343, 345 and
the import at line 12).

**Separate finding, and arguably the more actionable one:** the module carries
**two live `PYTHONHASHSEED`/insertion-order determinism hazards unrelated to
`shortest_path`** (§6). Both are currently unreachable on the production
board, but only by accident of the channel-ID format — not by any guard. This
is the same class as PR #730 ("make component placement independent of
`PYTHONHASHSEED`").

---

## Falsifiers, stated before measuring

Per `docs/evidence/2026-07-27-first-route-and-profile.md`'s convention, two
falsifiers were written down before any measurement was taken, because the
question has two independent halves and a single falsifier would have hidden
one of them.

**F1 — "the primitive is genuinely order-unstable here."** *Permuting
node/edge insertion order on the real board's channel skeleton, while holding
the node set, edge set, and weights identical, changes the path
`nx.shortest_path` returns for the endpoint pair `channel_mapping` queries.*

> **F1 FIRED.** 32/32 permutation seeds returned a different path; 31 distinct
> paths across 32 seeds; 256 tied minimum-hop paths exist between the queried
> endpoints. Details in §4. Every claim the survey made about this primitive
> was correct.

**F2 — "the instability is reachable."** *`_extract_waypoints` can be entered
with an empty `channel_sequence`, so the branch containing those calls can
execute.*

> **F2 DID NOT FIRE.** One call site, statically dominated by a `return None`
> guard on the same variable, with no rebinding in between (§2); zero
> executions of lines 339/343 under the test suite (§3) and under a
> production-format channel sequence (§5).

The verdict rests entirely on F2. That is a materially weaker foundation than
"order does not matter", and it is stated this way deliberately: if a future
change makes `_extract_waypoints` reachable with an empty sequence, the
blocker returns in full force. The mechanical guard against that is in §8.

---

## 0. Environment and provenance — read before trusting any number

Two caveats, both load-bearing.

**(a) The measurements ran against the shared checkout's `temper_placer`, not
this worktree's.** This branch is cut from `origin/main`
(`15110feccc6ec9389f0777d3cff1ce9f81b11068`), but `origin/main`'s Python calls
`temper_geometry.pad_core_half_extents_py` and
`temper_geometry.pad_bounding_radius_py`, which the built extension in the
available environment does not export. Building it is explicitly out of scope
for this spike (disk pressure; ~10 GB cold build). The importable
`temper_placer` therefore resolves to
`/Users/bennet/Desktop/temper/packages/temper-placer/src`.

This is safe for exactly this spike because the two files under measurement
are **byte-identical** across both trees:

| File | sha256 |
|---|---|
| `router_v6/channel_mapping.py` | `e622770bd3d6b17e34a6eb9875e1cc48a81f22a913abdbf30a6413c5bb46172a` |
| `router_v6/channel_skeleton.py` | `76fa677894361102020973d13b3a429a77803b88405d70f3bb20a7b10a7f141c` |

All *static* analysis (§2, §7) runs against this worktree at `15110fec` and is
unaffected either way.

**(b) The full production board route could not be completed**, for the same
missing-symbol reason — it fails in Stage 2 at
`core/pad_geometry.py:171`. This is recorded as **UNVERIFIED** in §9 rather
than papered over. §5 substitutes a narrower but exact measurement: the real
production channel-ID format applied to the real board's real skeleton.

**Pad-geometry shim.** §4 and §5 need a real channel skeleton, which needs
Stage 2. `pad_corner_radius` is forced to `0.0` (and `pad_core_half_extents`
to `(w/2, h/2)`). This is not invented behaviour: it is the `r <= 0.0` branch
of the production `pad_polygon`, which that module's own docstring documents
as the safe bounding-rectangle fallback taken for unrecognised pad shapes. It
makes pads marginally *larger*. It cannot manufacture the effect under test —
graph construction order is independent of pad corner rounding.

**Board:** `pcb/temper.kicad_pcb`, 169 components, 108 nets.
**networkx 3.6.1, shapely 2.1.2, Python 3.12.13.**

At measurement time the working tree contained only the untracked measurement
scripts added by this PR; every file under measurement was unmodified at
`15110fec`.

---

## 1. What the call sites actually are

`channel_mapping.py:339` and `:343`, inside `_extract_waypoints`:

```python
if not channel_sequence:                                    # 327
    if skeleton.graph.number_of_nodes() > 0:                # 328
        nodes = list(skeleton.graph.nodes())                # 330
        if len(nodes) >= 2:                                 # 332
            try:
                endpoints = [n for n in nodes if skeleton.graph.degree(n) == 1]
                if len(endpoints) >= 2:
                    path = nx.shortest_path(skeleton.graph, endpoints[0], endpoints[1])
                    return path                             # 339-340
                else:
                    path = nx.shortest_path(skeleton.graph, nodes[0], nodes[-1])
                    return path                             # 343-344
            except (nx.NetworkXNoPath, nx.NodeNotFound):    # 345
                return nodes[: min(5, len(nodes))]
    return []
```

Three properties of this code matter for the spike's question 2 ("length, or
waypoints?"):

1. **It is a waypoint path, not a length.** `return path` returns the node
   list *as* `_extract_waypoints`'s return value, and skeleton nodes are
   `(x, y)` float tuples (`channel_skeleton.py:31`). A different tied path is
   literally a different physical polyline. So the tie-insensitive escape
   hatch the brief hypothesised — "a path used only to compute a length" —
   **does not apply**. This is the tie-*sensitive* case.

2. **No `weight=` is passed.** `nx.shortest_path` therefore dispatches to
   unweighted `bidirectional_shortest_path`, not Dijkstra. The graph's `weight`
   edge attributes (`channel_skeleton.py:113`) are **ignored**. "Shortest"
   means fewest hops, not fewest millimetres. This makes ties *far* more
   common than the survey's "near-uniform edge weights" framing suggests —
   near-uniform weights produce near-ties, but equal hop counts produce exact
   ties, which is what §4 measures.

3. **`endpoints[0]`, `endpoints[1]`, `nodes[0]`, `nodes[-1]` are themselves
   insertion-order picks** off `list(graph.nodes())`. Even the *query* is
   order-dependent, before `shortest_path` is reached. §4 measures this
   separately.

---

## 2. M1 — the branch is statically unreachable

`tools/measurements/networkx_path_order/m1_static_reachability.py` checks a
dominance argument mechanically against the AST and **exits non-zero if any
step fails**, so a future edit that breaks the argument makes the measurement
fail loudly rather than go quietly stale.

| Check | Result |
|---|---|
| `nx.shortest_path` call lines in `_extract_waypoints` | `339`, `343` |
| Enclosing `if not channel_sequence:` block | lines `327`–`348` |
| All `nx` calls inside that block | **true** |
| Repo-wide call sites of `_extract_waypoints` | **1** (`channel_mapping.py:290`) |
| Caller | `_map_net_to_channels` |
| Guard `if not channel_sequence: return None` | line `286`, body index `3` |
| Call to `_extract_waypoints` | line `290`, body index `4` |
| Guard dominates call (same unconditional statement list, earlier index) | **true** |
| `channel_sequence` rebound between guard and call | **none** |
| **Verdict: nx branch statically unreachable** | **true** (exit 0) |

The argument in one line: the guard is an unconditional `return` in the
caller's top-level statement list, so any control flow reaching line 290 has a
truthy `channel_sequence`; `_extract_waypoints` has no other caller; therefore
its `if not channel_sequence:` test is always False.

The script also prints *every* syntactic reference to `_extract_waypoints`,
not just calls, so a reviewer can confirm nothing reaches it by aliasing or
attribute access. The only non-definition references in the repository are the
single call at line 290 and the deliberate monkeypatches inside this spike's
own `m2_live_route_trace.py`.

---

## 3. M2 — zero executions under the test suite

Line coverage of `channel_mapping.py` across the router_v6 tests that exercise
it (`test_channel_mapping`, `test_all_pad_tree_routing`, `test_wave3_skip_sat`,
`test_wave2_structural_small`, `test_phase1_anti_false_zero`,
`test_via_layer_properties_pbt` — 49 passed, 1 skipped):

```
Name                          Stmts   Miss Branch BrPart  Cover   Missing
channel_mapping.py              195     59     86     12    66%   ... 328-348, ... 384-385, ... 453->460
```

`328-348` — the entire dead branch, both `nx.shortest_path` calls and their
`except` handler — is in the *Missing* column. So is `384-385`, and `453->460`
records that the `number_of_nodes() <= 20` gate at line 453 always fell
through to `return None`. Those last two matter for §6.

This is corroboration, not proof: a test suite missing a branch shows only
that the tests do not cover it. The proof is §2; this rules out the case where
a dynamic dispatch defeats the static argument.

---

## 4. M3 — the counterfactual: if it *were* live, would order be observable?

This is the measurement that decides whether the survey was wrong or merely
looking at dead code. It perturbs entirely within Python — rebuild the *same*
graph (identical node set, edge set, and weights) with node and edge insertion
order permuted, then re-run the exact call the dead branch makes.

Skeletons are built by the **production** `extract_channel_skeleton` from the
**production** board. `compute_routing_space` emits routing spaces only for
layers whose stackup type is `signal`/`mixed`; on this board
`_extract_stackup` classifies `F.Cu` and `B.Cu` as `plane` and `In1.Cu` /
`In2.Cu` as `mixed`, so those two are the skeletons that exist. (That
classification is zone-content-driven with `use_declared_layer_roles=False`;
it is production behaviour, not a shim artifact, and chasing it is out of
scope.)

Both layers produce identical graphs:

| Property | Value |
|---|---|
| Nodes / edges | **7,046 / 9,042** |
| Connected | true |
| Degree-1 nodes (the `endpoints` list) | 540 |
| Endpoint rule taken | `degree1_endpoints` (`endpoints[0]`, `endpoints[1]`) |
| Baseline path length | 136 nodes |
| **Distinct tied minimum-hop paths between the queried endpoints** | **256** (exact, not capped) |
| **Permutation seeds returning a different path** | **32 / 32** |
| Distinct paths observed across 32 seeds | 31 |
| First index at which an example pair diverges | 17 (of 136) |
| Nodes present in one path but not the other | 4 each way |
| **Permutation seeds that also change the endpoint pair** | **32 / 32** |

Two independent order dependencies, then, not one:

- **Path selection.** 256 equally-short paths exist; which one comes back is
  decided by adjacency-dict insertion order feeding networkx's bidirectional
  BFS, and it flipped on every seed tried.
- **Endpoint selection.** `endpoints[0]` / `endpoints[1]` are picks off
  `list(graph.nodes())` among 540 degree-1 candidates, and they flipped on
  every seed too. Even a Rust port with a perfectly matched BFS tie-break
  would still have to reproduce the node-insertion order of the Voronoi
  medial-axis walk to pick the same *query*.

The two paths in the example differ at 4 of 136 nodes, i.e. the returned
waypoint polyline routes through 4 different physical coordinates. Under
Wave-4 gate G2's bit-exact `==` (`docs/wave4-discipline-contract.md` §3), that
is a hard failure, not a tolerance question.

**So the survey's classification was substantively correct about the
primitive.** This is the same class as the recorded `nx.minimum_cut`
partition-order keep in `packages/temper-geometry/VERIFICATION.md`. It is
dead code, which is why the verdict flips — not because the primitive is
benign.

---

## 5. M5 — what the *production* channel-ID format actually drives

§2 and §3 show the empty-`channel_sequence` branch never runs. This section
shows which branch does, and it also closes out §6's reachability question.

Production channel IDs are built by `constraint_model.py:299` as
`edge_id = f"{layer_name}_E{i}_{n1}_{n2}"`, where `n1`/`n2` are skeleton nodes
— `(x, y)` float tuples whose `str()` renders as `(1.5, 2.5)`. They reach
`channel_mapping` via `_pipeline_route.py:380`
(`uses_channels=list(topo_data.get("uses_channels", []))`), out of the Rust SAT
solver's `topology_graph`. A real ID:

```
In1.Cu_E0_(20.420476572060064, 21.883600792793096)_(20.405006840092657, 21.749159655296246)
```

Feeding 200 such IDs, built from the real skeleton's real edges, into the real
`_extract_waypoints`:

| Observation | Value |
|---|---|
| Channel IDs in / waypoints out | 200 → **400** (two per edge) |
| Edge-coordinate regex branch (line 356) executed | **true** |
| Edge-coordinate append (line 366) executed | **true** |
| `_parse_channel_coordinate` calls (line 374) | **0** |
| Line-385 insertion-order fallback executed | **false** |
| `nx.shortest_path` lines 339 / 343 executed | **false** / **false** |
| `number_of_nodes() <= 20` gate open | **false** (7,046 nodes) |

The `re.findall(r"\(([^)]+)\)", channel_id)` at line 356 finds two coordinate
groups, takes the edge branch, and `continue`s — so
`_parse_channel_coordinate` is never called at all, and `waypoints` is
non-empty, so the line-385 fallback is never reached either.

---

## 6. Latent determinism hazards in the current Python — a separate finding

The spike brief asked (question 4) whether the *current Python* has a
determinism issue independent of any migration. It does — two of them — and
neither involves `shortest_path`. Both are on live, non-dead code paths;
both are currently unreachable in production, but by accident of the
channel-ID format rather than by any guard.

**H1 — `hash()` salting at `channel_mapping.py:457`.**

```python
if skeleton.graph.number_of_nodes() <= 20:
    nodes = list(skeleton.graph.nodes())
    if nodes:
        idx = hash(channel_id) % len(nodes)
        return nodes[idx]
```

`hash()` of a `str` is salted per interpreter process by `PYTHONHASHSEED`. The
waypoint returned for a given channel ID is a different physical `(x, y)` on
different runs of identical input.

| Measurement (12 fresh interpreters, 5 channel IDs, 8-node skeleton) | Result |
|---|---|
| Distinct result sets, default environment | **12 / 12** |
| Distinct result sets with `PYTHONHASHSEED=0` | **1 / 3** |
| Hash randomisation active | true |

This is unambiguous: same input, same code, different geometry per process.
It is exactly the class PR #730 addressed for component placement.

**H2 — graph insertion order at `channel_mapping.py:385`.**

```python
return nodes[: min(len(channel_sequence) + 1, len(nodes))]
```

`list(graph.nodes())` is networkx insertion order, so this returns whichever
nodes the skeleton builder happened to insert first. Permuting node/edge
insertion order on an otherwise-identical 40-node graph: **16 / 16 trials
returned a different waypoint list.** Not salted, but not a property of the
board geometry either — it is a property of the order `channel_skeleton`
walked the Voronoi output.

**Reachability, honestly.** §5 measures both gates as closed on this board:
the skeleton has 7,046 nodes (H1 needs ≤ 20), and every production channel ID
parses via the edge-coordinate branch (H2 needs *all* IDs to fail to parse).
So neither fires on `pcb/temper.kicad_pcb` today. But H1's gate is a board-size
threshold, not an invariant — any board or test fixture whose skeleton has ≤ 20
nodes opens it — and H2's gate is "the SAT solver's channel-ID format keeps
containing two parenthesised coordinate groups", which is a coupling between
two modules that nothing checks. These are recorded as latent, not active.

---

## 7. M6 — what a Rust port would actually have to reproduce

With the dead branch deleted, `channel_mapping`'s only remaining contact with
networkx is lines 273–283:

```python
if (not channel_sequence
        and net_topology.path_graph is not None
        and net_topology.path_graph.number_of_edges() > 0):
    nodes = list(net_topology.path_graph.nodes())
    channel_sequence = [str(node) for node in nodes]
```

`path_graph` is a `nx.DiGraph` built at `_pipeline_route.py:371-374` by
`pg.add_edges_from(path_edges)` from the Rust solver's output. So the question
a port must answer is not "which shortest path" but the far narrower "what
order does `DiGraph.nodes()` yield?".

Measured: `list(DiGraph.nodes())` equals **first-seen order over the edge
list**, 200/200 randomised trials, networkx 3.6.1. That is a deterministic,
trivially portable rule with no algorithmic tie-breaking in it — a `Vec` plus
a seen-set. It is not in the same class as `shortest_path` at all.

Caveat: this is an empirical check of documented dict-insertion-order
behaviour on one networkx version, not a stability guarantee across versions.
A port should pin it with a differential test rather than rely on this row.

---

## 8. Recommendations

Per the spike's constraints, these are **recommendations only** — no ledger,
baseline, or verdict file was edited by this PR.

1. **Reclassify `channel_mapping.py` BLOCKED → PORT** in the survey's bucket
   table (`docs/evidence/2026-08-04-router-v6-migration-survey.md` §2.3, PR
   #741, currently unmerged). **203 stmts / 178 exec** move. The BLOCKED
   bucket drops from 1,753 to 1,550 stmts.

2. **Delete the dead branch (`channel_mapping.py:327-348`) *before* porting,
   in its own PR, as a behaviour-preserving change.** M1 is the proof it is
   unreachable and doubles as the regression check. This removes `networkx`
   from the module entirely — measured: after line 12's import, the only `nx`
   references in the file are 339, 343, 345.
   **Do not port the branch.** §4 shows its behaviour is not a stable target
   even within Python, so any Rust implementation would be pinned against a
   moving reference under gate G2's `==`.

3. **Keep the `networkx` blocker open for `topology_extraction.py`** (56 stmts).
   Its `nx` use is live (lines 22, 97), it is out of scope here by instruction,
   and another agent is concurrently retiring its unreachable functions. Of the
   259 stmts the survey attributed to this blocker, 203 move and 56 do not.

4. **Add a guard so the dominance argument cannot silently rot.** M1 already
   exits non-zero when it breaks; wiring it into the invariant suite is a
   ~1-line change and is the cheapest possible protection for the fact that
   this verdict rests on reachability (F2) rather than on safety.

5. **Treat H1 (§6) as a real determinism defect on its own track**, separate
   from any migration. `hash(channel_id) % len(nodes)` is indefensible as a
   coordinate-selection rule regardless of reachability — it returns a
   *geometric position* from a salted hash. The obvious fix is a stable key
   (e.g. sorted node order plus a non-salted digest), which is also a
   prerequisite for porting the function at all. H2 is lower severity but
   should be pinned by a sorted or explicitly-ordered node list.

---

## 9. What I could not verify

- **The full production board route did not complete** (§0b) — Stage 2 fails
  at `core/pad_geometry.py:171` because the built `temper_geometry` predates
  `origin/main`'s Python, and building it was out of scope. So there is **no
  end-to-end run of `route_pcb` in this spike**. §5's production-format census
  is a narrower substitute: it exercises the real function on real skeleton
  data in the real ID format, but it does not prove that the SAT solver never
  emits an empty `uses_channels` *together with* an empty `path_graph`. That
  case is handled by `_map_net_to_channels` returning `None` at line 287
  before `_extract_waypoints` is reached — which is the §2 argument again, so
  the conclusion holds, but it is reached statically rather than observed.

- **Spike question 3 — does divergence reach an observable output — is
  answered only conditionally, and the boundary is named here.** Because the
  branch is dead, no divergence propagates at all today, so the question is
  moot in the current code. I did **not** trace whether differing waypoints
  would survive the corridor/A\* stage, because doing so would have required
  the end-to-end route that §0b blocks. What §4 does establish is that the
  divergence is real *at the `_extract_waypoints` boundary* — 4 differing
  coordinates out of 136 — and `_astar_heuristics.py:73,152` and
  `_astar_reconstruct.py:182` consume `ChannelPath.waypoints` directly, so the
  values do feed A\*. Whether A\* washes them out is **UNKNOWN**.

- **Only the two `mixed` layers were measured** (§4). `F.Cu`/`B.Cu` are
  classified `plane` on this board and get no routing space. Whether a board
  whose outer layers are `signal` produces a materially different skeleton is
  unmeasured; the tie counts here should not be read as universal.

- **A full-suite coverage run over all of `tests/router_v6/` was started but
  had not finished** when this document was written; §3 reports the targeted
  subset that actually exercises the module. The subset is what carries the
  claim, and §2 is what carries the proof.

- **networkx version stability** (§7) is checked empirically on 3.6.1 only.

---

## 10. Reproducing

Scripts live in `tools/measurements/networkx_path_order/`. Each writes a JSON
result and prints it. M1 and M5 need no network and no board; M3 and M5 need
`pcb/temper.kicad_pcb`.

```bash
# M1 -- static reachability proof (exits non-zero if dominance breaks)
python3 tools/measurements/networkx_path_order/m1_static_reachability.py \
    --repo . --out m1.json

# M2 -- dynamic reachability under the test suite
python3 -m pytest packages/temper-placer/tests/router_v6/test_channel_mapping.py \
    packages/temper-placer/tests/router_v6/test_all_pad_tree_routing.py \
    packages/temper-placer/tests/router_v6/test_wave3_skip_sat.py \
    packages/temper-placer/tests/router_v6/test_wave2_structural_small.py \
    packages/temper-placer/tests/router_v6/test_phase1_anti_false_zero.py \
    packages/temper-placer/tests/router_v6/test_via_layer_properties_pbt.py \
    --cov=temper_placer.router_v6.channel_mapping --cov-report=term-missing

# M3 -- tie census + permutation experiment on the real skeleton
python3 tools/measurements/networkx_path_order/m3_tie_and_permutation.py \
    --pcb pcb/temper.kicad_pcb --out m3.json --seeds 32

# M4 -- latent PYTHONHASHSEED / insertion-order hazards
python3 tools/measurements/networkx_path_order/m4_latent_determinism.py \
    --out m4.json --trials 12

# M5 -- which branch the production channel-ID format drives
python3 tools/measurements/networkx_path_order/m5_production_branch_census.py \
    --pcb pcb/temper.kicad_pcb --out m5.json

# M6 -- DiGraph.nodes() ordering rule
python3 tools/measurements/networkx_path_order/m6_digraph_node_order.py --out m6.json

# M7 -- statements moving bucket + remaining networkx surface
python3 tools/measurements/networkx_path_order/m7_stmt_and_nx_surface.py \
    --repo . --out m7.json
```

`m2_live_route_trace.py` is included for completeness — it is the end-to-end
route probe described in §0b. It runs, instruments correctly, and reports
`route_error: AttributeError: module 'temper_geometry' has no attribute
'pad_bounding_radius_py'` in this environment. It should reproduce the §5
result directly once `temper_geometry` is rebuilt against `origin/main`.
