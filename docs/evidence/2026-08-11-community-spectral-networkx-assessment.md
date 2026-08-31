<!-- provenance: commit=670a751f35de8a9e01dbd1330729b2d99aeb77c2 dirty=false -->
<!-- measured_at_commit: 670a751f3 (branch: fanout12/work-3, off origin/main) -->

# Spike S6: `core/community.py` and `heuristics/spectral.py` — migration-or-keep assessment

**Date:** 2026-08-11
**Surfaces:**
- `packages/temper-placer/src/temper_placer/core/community.py` (153 LOC) — Louvain community detection + Kernighan-Lin bisection
- `packages/temper-placer/src/temper_placer/heuristics/spectral.py` (166 LOC) — Spectral layout initialization heuristic
**Scope:** a verdict plus its measurements. **No production code was changed, no Rust was written, and no Rust crate was built.**

**Context:** This is the gate for whether the two remaining algorithmic `networkx` surfaces can be migrated to Rust, kept as REQUIRED-PYTHON, or deleted. Precedents: S3 (shortest_path → DELETE dead code), S4 (connected_components → PORT), S5 (cycle_basis → DELETE dead code).

---

## Verdict

**BOTH surfaces are dead code. Neither is reachable from the production pipeline. Recommendation: DELETE both, plus the unused `python-louvain` dependency.**

| Surface | LOC | Verdict | Key reason |
|---|---|---|---|
| `core/community.py` | 153 | **DELETE** | 0 production call sites; unused third-party dep (`python-louvain`); functions non-deterministic even if reached |
| `heuristics/spectral.py` | 166 | **DELETE** | Shadowed factory; the exported `create_default_pipeline` does NOT register it; spectral layout is order-sensitive |

Separate finding: `heuristics/pipeline.py` defines a `create_default_pipeline` that IS shadowed by `heuristics/__init__.py`'s identically-named function. The shadowed version registers `SpectralPlacementHeuristic`; the exported version does not. This is a latent defect — code that appears to be wired into the pipeline is not, and a future edit that changes the import path could silently activate dead, order-sensitive code. See §7.

---

## Falsifiers, stated before measuring

Per the S3/S4/S5 convention, falsifiers were written down before measurement.

### Community surface

**F-C1 (Louvain determinism) — "`best_partition(G, random_state=42)` is deterministic across interpreter runs and insertion orders."**

> **F-C1: PARTIALLY FIRED.** Deterministic across fresh interpreters when using `nx.from_numpy_array` (1 distinct partition, 20 runs, §4.A). Order-sensitive when graph built with permuted insertion order (6–8 distinct partitions, 32 seeds, §4.B). Modularity score also varied on the random graph (3 distinct values). The production path (`from_numpy_array`) is deterministic; any alternative graph construction is not.

**F-C2 (KL determinism) — "`kernighan_lin_bisection` produces deterministic output on the same graph."**

> **F-C2: FIRED.** 2–5 distinct partitions from 100 repeated calls on the SAME graph (§5.A). KL uses random initial partitions and is fundamentally non-deterministic.

**F-C3 (community reachability) — "`detect_communities` or `partition_netlist_min_cut` are called from production code."**

> **F-C3: DID NOT FIRE.** 0 production call sites for either function (§3). `detect_communities` is exported but unused. `partition_netlist_min_cut` is not even exported.

### Spectral surface

**F-S1 (spectral sign stability) — "`spectral_layout` produces identical coordinates across interpreter runs and insertion orders."**

> **F-S1: PARTIALLY FIRED.** Identical across fresh interpreters (1 distinct coordinate set, 10 runs, §6.A). Order-sensitive across insertion orders (4 distinct coordinate sets, 32 seeds, §6.B). However, the differences are ONLY orthogonal transformations (rotation/reflection): Procrustes disparity ≈ 1e-15, distance correlation = 1.0 (§6.C). The relative geometry is preserved; only absolute coordinates differ.

**F-S2 (spectral reachability) — "`SpectralPlacementHeuristic` is reachable from the production pipeline."**

> **F-S2: DID NOT FIRE.** The heuristic is registered in `heuristics/pipeline.py:create_default_pipeline()` (line 376) and `create_priority_pipeline()` (line 417), but both functions are SHADOWED by `heuristics/__init__.py`'s `create_default_pipeline()` which does NOT register it (§3). No production code imports from `heuristics.pipeline` directly. The exported pipeline never includes spectral.

---

## 0. Environment and provenance

The measurements ran against the main checkout's `.venv` Python 3.12. The worktree's Python 3.9 cannot import `temper_placer` (missing `TypeAlias` from `typing`) and lacks `python-louvain`.

The files under measurement are **byte-identical** across both trees (main checkout at `/home/bennet/Desktop/temper` and this worktree at `/tmp/opencode/wt-f12-3`, both at `670a751f3`):

| File | sha256 |
|---|---|
| `core/community.py` | `a4a6300e1cf88ceb767fd164bb999b5144be213c00f26910b4e66a1e321f54f6` |
| `heuristics/spectral.py` | `427152530f7be239fa3c3ab84815de2f17e3c745cdd7c43433be3de09a6d983e` |
| `heuristics/pipeline.py` | `e7bcfd4ad8fcfb07bcd41b5f4f55faa3c9f8aaf5c9a8e8e4b409b893c1814e3e` |
| `heuristics/__init__.py` | `ea7abfd1f9b5e12caa8bf0af6f2f9eb2d842d91f6e0fe9c1bdcd68833f22766e` |

Verification:
```bash
sha256sum packages/temper-placer/src/temper_placer/core/community.py
sha256sum packages/temper-placer/src/temper_placer/heuristics/spectral.py
sha256sum packages/temper-placer/src/temper_placer/heuristics/pipeline.py
sha256sum packages/temper-placer/src/temper_placer/heuristics/__init__.py
```

**networkx 3.6.1, python-louvain 0.16, numpy 2.3.5, Python 3.12.3.**

At measurement time the working tree contained only untracked measurement scripts added by this PR; every file under measurement was unmodified at `670a751f3`.

---

## 1. What the surfaces actually are

### 1.A `core/community.py` — 153 LOC

Two functions, both using `build_adjacency_matrix` → `nx.from_numpy_array` → algorithmic graph operation:

| Function | LOC | Algorithm | Deps | Deterministic? |
|---|---|---|---|---|
| `detect_communities` | 42–93 | Louvain (`community_louvain.best_partition`, `random_state=42`) | `python-louvain`, `networkx` | Yes via `from_numpy_array`; no with insertion-order perturbation |
| `partition_netlist_min_cut` | 101–153 | Kernighan-Lin (`nx.community.kernighan_lin_bisection`) | `networkx` only | No — random initial partitions |

Also defines two dataclasses: `Community` (20 LOC, exported), `ComponentCommunity` (10 LOC, not exported).

The `python-louvain` package (`community`) is a declared dependency (`pyproject.toml` line 35: `"python-louvain>=0.16"`) used **only** by this module. The `nx.community.kernighan_lin_bisection` caller is similarly the only use of that networkx submodule in the repository.

### 1.B `heuristics/spectral.py` — 166 LOC

One class, `SpectralPlacementHeuristic(Heuristic)`, with:
- `apply()` (62–134 LOC): builds a `GraphBuilder` graph, computes `nx.spectral_layout` per connected component, scales/positions components on the board grid.
- `_convert_to_placements()` (136–166 LOC): bounds-checking coordinate-to-placement conversion.

`nx.spectral_layout` calls `scipy.sparse.linalg.eigsh` under the hood — an ARPACK eigenvalue solver. The Fiedler vector (second eigenvector of the graph Laplacian) is defined only up to sign.

---

## 2. The `create_default_pipeline` shadowing issue — a separate finding

This surfaced during reachability analysis and is load-bearing for the verdict:

- `heuristics/pipeline.py:359` defines `create_default_pipeline()` which registers `SpectralPlacementHeuristic` (line 376).
- `heuristics/__init__.py:62` defines its OWN `create_default_pipeline()` which does NOT register spectral.
- `heuristics/__init__.py` exports ONLY its own version (line 146: `"create_default_pipeline"`).
- Production code calls `heuristics.create_default_pipeline()` → `__init__.py` version (no spectral).
- `pipeline.py`'s version is only reachable via `from temper_placer.heuristics.pipeline import create_default_pipeline` — used only in tests.

The docstring of `pipeline.py:create_default_pipeline` (lines 362–369) says "This factory includes: 1. Spectral Layout (Initial global placement)" — the **code** includes it, but the **exported API** does not. A future edit that changes the import path (e.g., refactoring `__init__.py` to re-export `pipeline.create_default_pipeline` instead of defining its own) would silently activate the spectral heuristic in production, with all its order-sensitivity (§6).

Similarly, `create_priority_pipeline()` (line 383) registers spectral at line 417 but is not exported from `__init__.py` at all.

---

## 3. M3 — reachability analysis

`tools/measurements/community_spectral_assessment/m3_reachability.py`:

### Community reachability

| Function | Src call sites | Test call sites | Exported? |
|---|---|---|---|
| `detect_communities` | **0** | 4 | Yes (`core.__init__.__all__`) |
| `partition_netlist_min_cut` | **0** | 3 | No |

`detect_communities` is exported from `core/__init__.py` at line 26 and listed in `__all__` at line 178, but no production module imports or calls it. The only references in `src/` are the definition and the re-export. All call sites are in test files:
- `tests/core/test_community.py` (3 calls)
- `tests/core/test_core_graph_cluster_rust_differential.py` (1 call)

`partition_netlist_min_cut` is not exported at all (not in `core.__init__.__all__`). Its only callers are in `tests/core/test_community_coverage.py` (3 calls).

### Spectral reachability

`SpectralPlacementHeuristic` has 2 "call sites" in `src/` — both are constructor calls in `heuristics/pipeline.py` (lines 376 and 417). But as established in §2, the factory functions containing these calls are shadowed. The exported `heuristics.create_default_pipeline` does NOT use spectral. `SpectralPlacementHeuristic` is NOT in `heuristics.__init__.__all__`.

Production code that calls `heuristics.create_default_pipeline()`:
- `tests/heuristics/test_topological_integration.py` (19 calls)
- `tests/heuristics/test_pipeline.py` (5 calls)
- `tests/heuristics/test_coverage_paydown.py` (3 calls)

All callers are test files. The one production reference (`cli/timing_gate.py:281`) imports `RouterV6Pipeline`, not the heuristic pipeline.

**Verdict: neither surface is reachable from the production pipeline.**

---

## 4. M1 — Louvain determinism (F-C1)

`tools/measurements/community_spectral_assessment/m1_louvain_determinism.py`:

### A: Fresh-interpreter determinism (`from_numpy_array`)

Same graph (8-node bridged cliques), `from_numpy_array` → `best_partition(random_state=42)`, 20 fresh interpreters with different `PYTHONHASHSEED` values:

| Graph | Runs | Distinct partitions | Distinct modularities | Deterministic? |
|---|---|---|---|---|
| 8-node bridged cliques | 20 | **1** | **1** (0.4012) | **Yes** |
| 15-node random thresholded | 20 | **1** | **1** (0.0253) | **Yes** |

`random_state=42` successfully pins the Louvain algorithm's random decisions. The greedy agglomerative process reaches the same local optimum every time.

### B: Insertion-order perturbation

Same graphs, but nodes and edges added in permuted order (32 seeds):

| Graph | Seeds | Distinct partitions | Distinct modularities | Order-stable? |
|---|---|---|---|---|
| 8-node bridged cliques | 32 | **6** | 1 | **No** |
| 15-node random thresholded | 32 | **8** | **3** | **No** |

When graph construction order varies, the Louvain algorithm finds different community assignments. The modularity score also varies on the random graph (3 distinct values: 0.0164, 0.0253, 0.0394). The 6 distinct partitions for the house graph are actually the same 3 communities with permuted labels (community IDs 0,1,2 assigned differently).

The production path (`from_numpy_array`) avoids this because the adjacency matrix construction is deterministic. But any alternative graph construction (e.g., building the graph edge-by-edge from a different source) would expose this instability.

### C: Within-process stability

50 repeated calls on the same `nx.Graph` object: **1 distinct partition.** The same graph object always produces the same result. The instability in (B) comes from different graph construction, not from the algorithm's internal randomness when `random_state` is fixed.

---

## 5. M2 — KL bisection determinism (F-C2)

`tools/measurements/community_spectral_assessment/m2_kl_determinism.py`:

### A: Same graph, repeated calls

| Graph | Calls | Distinct partitions | Deterministic? |
|---|---|---|---|
| 8-node bridged cliques | 100 | **2** | **No** |
| 12-node random thresholded | 100 | **5** | **No** |

`kernighan_lin_bisection` uses random initial bipartitions. There is no `random_state` parameter to pin it. The same graph, same weights, same call produces different bisections on different invocations — even within the same process and the same `nx.Graph` object.

### B: Insertion-order perturbation

| Graph | Seeds | Distinct partitions |
|---|---|---|
| 8-node bridged cliques | 64 | 2 |
| 12-node random thresholded | 64 | 4 |

Both insertion order AND internal randomness contribute to non-determinism. KL is fundamentally unstable as a deterministic algorithm — it's a heuristic that searches from random starts.

---

## 6. M4/M5 — Spectral layout sign stability (F-S1)

`tools/measurements/community_spectral_assessment/m4_spectral_sign.py` and `m5_spectral_tie_census.py`:

### A: Fresh-interpreter determinism

Same graph (canonical edge order), `spectral_layout(weight="weight", dim=2)`, 10 fresh interpreters:

| Graph | Runs | Distinct coordinate sets | Deterministic? |
|---|---|---|---|
| 8-node 11-edge | 10 | **1** | **Yes** |
| 7-node 10-edge (star+ring) | 10 | **1** | **Yes** |

`eigsh` (ARPACK) is deterministic for the same graph and same `PYTHONHASHSEED`-independent LAPACK calls. Eigenvector sign conventions are not perturbed across fresh interpreters for these graphs.

### B: Insertion-order perturbation

| Graph | Seeds | Distinct raw coord sets | Distinct sign-normalized |
|---|---|---|---|
| 8-node 11-edge | 32 | **4** | **4** |
| 7-node 10-edge | 32 | **4** | **2** |

Graph construction order changes the adjacency-dict order, which changes the Laplacian matrix row/column order, which can produce different eigenvector outputs. Sign normalization reduces the star+ring graph from 4 to 2 distinct sets (the remaining difference is a non-sign-flip coordinate difference).

### C: Procrustes analysis — are the differences orthogonal transforms only?

| Graph | Procrustes disparity (min/max) | Distance correlation (min/max) | Interpretation |
|---|---|---|---|
| 8-node 11-edge | 3e-16 / 4e-15 | 1.0 / 1.0 | **IDENTICAL_UP_TO_ORTHOGONAL** |
| 7-node 10-edge | 7e-16 / 2e-15 | 1.0 / 1.0 | **IDENTICAL_UP_TO_ORTHOGONAL** |

The Procrustes disparity (minimum RMSE after optimal orthogonal alignment) is effectively zero (~1e-15, at floating-point precision). The pairwise distance correlation is exactly 1.0. This means the **relative geometry is perfectly preserved** — different insertion orders produce layouts that differ only by rotation, reflection, and possibly a global sign flip. All pairwise distances between nodes are identical.

**This is a fundamentally different class from `shortest_path` (S3) or `cycle_basis` (S5).** Those primitives produced materially different outputs under insertion-order perturbation. Spectral layout produces the same geometry up to an orthogonal transformation. The downstream scaling+translation step in `apply()` (lines 103–125) would produce different absolute board positions but the same relative component arrangement.

### D: Within-process stability

50 repeated calls on the same `nx.Graph`: **1 distinct coordinate set.** Deterministic within a process.

### E: Sign conventions across LAPACK versions

This spike could NOT test across LAPACK versions (only one environment available). The eigenvector sign convention (each eigenvector is defined only up to ±1) is documented to vary across LAPACK implementations. A sign flip on one axis would rotate/reflect the layout by 180° on that axis but would preserve pairwise distances — the Procrustes analysis shows this class of difference is harmless. However, for graphs with degenerate eigenvalues (multiple eigenvectors sharing the same eigenvalue), the subspace spanning those eigenvectors can rotate arbitrarily, potentially producing genuinely different relative layouts. This was not observed on the tested graphs but is theoretically possible.

---

## 7. The `create_default_pipeline` shadowing defect — detailed

This is a separate finding that is load-bearing for the spectral verdict but actionable independently:

```
heuristics/__init__.py          heuristics/pipeline.py
─────────────────────────       ───────────────────────
create_default_pipeline()       create_default_pipeline()   ← SHADOWED
  ├─ TopologicalInit               ├─ SpectralPlacement    ← dead code
  ├─ KeepoutAwareness              └─ (empty otherwise)
  ├─ ConnectorEdgeSnapping
  ├─ ThermalEdgePlacement      create_priority_pipeline()   ← not exported
  ├─ CriticalLoop                  ├─ PowerStageTemplate
  ├─ FunctionalModuleCluster       ├─ DriverProximity
  ├─ PowerFlowTopology             └─ SpectralPlacement    ← dead code
  ├─ DecouplingCap
  ├─ DomainSeparation
  ├─ StarGroundTopology
  └─ SignalFlowPreservation
```

The docstring of `pipeline.py:create_default_pipeline` (lines 362–369) explicitly documents spectral as included — _"This factory includes: 1. Spectral Layout (Initial global placement)"_ — but the code path that executes in production never calls this function. The docstring is correct about its own function but misleading when read alongside `__init__.py`'s shadowing version.

**Risk:** A future refactoring that changes `__init__.py` to `from temper_placer.heuristics.pipeline import create_default_pipeline` (deleting the local definition) would silently activate `SpectralPlacementHeuristic` in production. The heuristic has order-sensitive output (§6.B) and uses `networkx` (the very dependency this migration program is removing).

**Recommendation:** Delete `pipeline.py:create_default_pipeline` (which has no unique purpose — its only registered heuristic is spectral, and `__init__.py`'s version is the production one) and either delete `create_priority_pipeline` or remove spectral from it. This eliminates the shadowing hazard.

---

## 8. What this means for the networkx migration

### Community module (`core/community.py`)

| Line(s) | Content | Disposition |
|---|---|---|
| 12 | `import community as community_louvain` | **Remove** — last use of this package |
| 13 | `import networkx as nx` | **Remove** — not needed elsewhere in this file after deletion |
| 14 | `import numpy as np` | Keep if needed by other modules; this file goes away |
| 19–25 | `class Community` | Used by tests and exported API; move to a stub if needed |
| 28–39 | `class ComponentCommunity` | Not exported; delete |
| 42–93 | `detect_communities` | **DELETE** |
| 96–98 | `get_community_component_indices` | **DELETE** (only called by `detect_communities`) |
| 101–153 | `partition_netlist_min_cut` | **DELETE** |

After deletion: the `python-louvain` dependency can be removed from `pyproject.toml`. The `Community` dataclass (used by tests and re-exported) could move to a minimal stub or be kept in a reduced `community.py`.

### Spectral module (`heuristics/spectral.py`)

| Line(s) | Content | Disposition |
|---|---|---|
| 12 | `import networkx as nx` | **Remove** |
| 27–166 | `SpectralPlacementHeuristic` | **DELETE** — entire class |

The `GraphBuilder` class in `heuristics/graph_utils.py` (85 LOC) is only used by `SpectralPlacementHeuristic`. After deletion, `graph_utils.py` becomes dead code as well — another 85 LOC removal and another `import networkx as nx`.

### Pipeline cleanup

| File | What | Disposition |
|---|---|---|
| `heuristics/pipeline.py:359-380` | `create_default_pipeline` (shadowed) | **DELETE** — no unique purpose; its only heuristic is spectral |
| `heuristics/pipeline.py:383-418` | `create_priority_pipeline` | Remove spectral from it, or delete entirely (not exported, only tested) |

### Total removable surface

| Item | LOC |
|---|---|
| `core/community.py` (full file) | 153 |
| `heuristics/spectral.py` (full file) | 166 |
| `heuristics/graph_utils.py` (orphaned) | 85 |
| `heuristics/pipeline.py` (shadowed factory) | ~40 |
| **Total** | **~444 LOC** |
| **networkx imports removed** | 3 (`community.py`, `spectral.py`, `graph_utils.py`) |
| **Python dependencies removed** | 1 (`python-louvain`) |

---

## 9. Classification against the strategy's REQUIRED-PYTHON category

Per `docs/evidence/2026-08-09-python-over-rust-interrogation.md` §2:

| Surface | Class | Rationale |
|---|---|---|
| `core/community.py` | **Not REQUIRED-PYTHON** | Neither `ortools`, `pydantic`, `click/rich`, `ngspice`/`kicad-cli` subprocess, nor a recorded keep. Dead code using `networkx` + `python-louvain`. |
| `heuristics/spectral.py` | **Not REQUIRED-PYTHON** | Uses `nx.spectral_layout` → `scipy.sparse.linalg.eigsh` (ARPACK) under the hood — this is a scipy dependency, but the function is dead code. If it were live, the scipy/ARPACK boundary would be a candidate for REQUIRED-PYTHON (the scipy-EDT/SuperLU keeps in §4.7 of the strategy doc), but dead code does not earn a keep. |
| `heuristics/graph_utils.py` | **Not REQUIRED-PYTHON** | Pure `networkx` graph construction. Dead code (orphaned by spectral deletion). |

Neither surface qualifies for REQUIRED-PYTHON. Both are dead code with no production callers.

---

## 10. Recommendations

1. **DELETE `core/community.py`** (153 LOC). Remove `python-louvain` from `pyproject.toml`. If the `Community` dataclass is needed by downstream consumers, move it to a minimal stub; the import path `temper_placer.core.Community` currently has 0 production callers.

2. **DELETE `heuristics/spectral.py`** (166 LOC). Remove the `import networkx as nx`.

3. **DELETE `heuristics/graph_utils.py`** (85 LOC). Orphaned by spectral deletion — `GraphBuilder` has no other callers.

4. **DELETE `heuristics/pipeline.py:create_default_pipeline`** (lines 359–380). The shadowed function has no unique purpose — its only registered heuristic is spectral, and the production pipeline is `__init__.py`'s version. This eliminates the shadowing hazard.

5. **Remove spectral from `create_priority_pipeline`** (lines 416–417) or delete the function entirely if it has no production callers.

6. **Remove `python-louvain>=0.16`** from `packages/temper-placer/pyproject.toml` line 35.

7. **Add regression guards** (recommended, not required for this spike):
   - A static assertion that `heuristics/__init__.py` does NOT import `SpectralPlacementHeuristic` (or any spectral-related name).
   - A static assertion that `core/__init__.py` does NOT import `detect_communities` (or remove it from `__all__`).

8. **Document the spectral layout finding for posterity.** If spectral placement is ever re-implemented (in Rust or Python), the key finding is that `spectral_layout` with `eigsh` is order-sensitive for absolute coordinates but preserves relative geometry up to orthogonal transforms. A Rust port using `nalgebra`/`faer`'s eigenvalue solvers would need to address sign conventions and degenerate eigenspaces. The Procrustes analysis in §6.C provides a differential test strategy: compare pairwise distance matrices, not absolute coordinates.

---

## 11. What I could not verify

- **Other boards.** Only code-level reachability was measured. The finding that neither surface is called from production is a static analysis result, not board-dependent. The tests that exercise these surfaces use synthetic netlists, not real PCB data.

- **LAPACK version stability of `spectral_layout`.** Only one Python/networkx/scipy version was tested (Python 3.12.3, networkx 3.6.1). The eigenvector sign convention is known to vary across LAPACK implementations. The Procrustes analysis (§6.C) shows this class of difference is harmless for relative geometry, but degenerate eigenspaces could produce genuinely different layouts in edge cases.

- **`build_adjacency_matrix` return type.** This function is a Rust re-export (`core/netlist.py:59: build_adjacency_matrix = _rs.build_adjacency_matrix`). The community module's docstring says it returns a "JAX Array" but the actual return type in the current codebase was not verified (the worktree's Python cannot import `temper_placer`). This is moot since the module is being deleted.

- **Full end-to-end production route with spectral active.** Not attempted — the spectral heuristic is not reachable, so there is no divergence to propagate. If it were reachable, the orthogonal-transform-only nature of the layout differences suggests downstream effects would be limited to rotation/reflection of component groups, which the CP-SAT solver would likely wash out (same relative distances → same wirelength → same objective). But this is UNVERIFIED.

- **`networkx` version stability of `from_numpy_array`.** Tested only on networkx 3.6.1. The adjacency-matrix-to-graph conversion is a simple documented API; version instability is unlikely but not formally verified.

---

## 12. Reproducing

Scripts live in `tools/measurements/community_spectral_assessment/`. All use only `networkx` + `numpy` + `python-louvain` and run on any Python with those packages installed.

```bash
# Use the main checkout's venv (has python-louvain installed)
PYTHON=/home/bennet/Desktop/temper/.venv/bin/python3

# M1 — Louvain determinism
$PYTHON tools/measurements/community_spectral_assessment/m1_louvain_determinism.py \
    --out m1.json --seeds 32 --fresh-runs 20

# M2 — KL bisection determinism
$PYTHON tools/measurements/community_spectral_assessment/m2_kl_determinism.py \
    --out m2.json --seeds 64 --repeat-calls 100

# M3 — Reachability analysis (runs on any Python 3.9+)
python3 tools/measurements/community_spectral_assessment/m3_reachability.py \
    --repo . --out m3.json

# M4 — Spectral layout sign stability
$PYTHON tools/measurements/community_spectral_assessment/m4_spectral_sign.py \
    --out m4.json --seeds 32 --fresh-runs 10

# M5 — Spectral tie census (Procrustes correlation)
$PYTHON tools/measurements/community_spectral_assessment/m5_spectral_tie_census.py \
    --out m5.json --seeds 64
```
