---
module: temper_placer
date: "2026-07-05"
problem_type: architecture_pattern
component: placer
severity: high
applies_when:
  - "When deleting a framework dependency (JAX, TensorFlow, PyTorch) that permeates dozens of modules"
  - "When migrating from gradient-based optimization to discrete constraint solving"
  - "When a core dataclass (PlacementState) carries framework-specific array types through 37+ importers"
symptoms:
  - "Framework imports are hard dependencies, not try/except graceful-degradation"
  - "Deleting a module breaks seemingly unrelated files through transitive import chains"
  - "Deletion leaves dead code paths with broken references to deleted modules"
root_cause: framework_migration
resolution_type: architecture_pattern
tags:
  - jax-retirement
  - dead-code-deletion
  - array-migration
  - dependency-graph
  - strangler-pattern
  - cli-flag-deprecation
  - worktree-closure
---

# JAX Framework Retirement: Reverse-Topological Deletion

## Problem

The Temper placer was built on JAX gradient-descent optimization (optax, flax, jax.numpy). The paradigm swap to CP-SAT discrete constraint solving required deleting the entire JAX stack — optimizer (21 files), losses (43 files), placement (7 files), loss_bridge.py, and force_directed heuristics — while keeping the rest of the pipeline functional. JAX was a hard dependency: 82+ files imported it directly, with zero try/except graceful-degradation patterns. The core `PlacementState` dataclass used `jax.Array` type hints consumed by 37 importers.

## Solution

**Five-stage deletion, with the critical relocation (U1) running first:**

### 1. Relocate shared utilities before any deletions (U1)

`_resolve_to_indices` lived in `loss_bridge.py` but was imported by `sat_bridge.py:109` and `parser.py:82` — pure-Python reference resolution with no JAX dependency. Extract to `pcl/resolver.py` first. If `loss_bridge.py` is deleted before consumers are ported, both the SAT bridge and PCL parser break.

### 2. Build the import dependency graph (U2)

Run `rg` across the full source tree to identify every file importing from the deletion targets. Classify each consumer:
- **Delete entirely**: leaf files with no surviving callers
- **Modify**: files that share code between JAX and non-JAX paths
- **Keep as-is**: JAX-free files unaffected by the deletion

The deletion order is reverse-topological: leaf files first, then support files, then core directories. Each sub-unit is a commit that passes CI independently.

### 3. Delete in reverse-topological order (U3)

Delete `force_directed.py` → `loss_bridge.py` → `losses/` → `placement/` → `optimizer/`. Before deleting `placement/`, resolve `router_v6/pipeline.py:29` which imported `Legalizer` from it. Each file or directory gets its own `git rm` commit.

### 4. Decouple core types from JAX (U5)

`PlacementState` (in `core/state.py`) had `positions: Array`, `rotation_logits: Array`, and `net_virtual_nodes: Array | None` — all JAX types. Three changes:
- Replace `from jax import Array` with `numpy.ndarray`
- Remove JAX-only methods: `random_init()` (used `jax.random`), `sample_rotation()` (used `jax.lax.stop_gradient`), `get_rotation_angles()` (Gumbel-Softmax)
- Add `from_positions_dict(dict[str, tuple[float, float]]) -> PlacementState` factory for CP-SAT output
- 37 importing files require mechanical `Array` → `ndarray` type updates

Pattern: replace JAX-dependent methods with pure-Python free functions, following the `pad-position-ssot` precedent.

### 5. Dead-code cleanup after the transition (post-review)

After deletion, the `temper optimize` CLI command had `sys.exit(0)` with ~3,000 lines of dead code below it containing 15+ broken imports from deleted modules. The `refinement_stage.py` `update_fn` closure still referenced `optax.adam()` and `jax.value_and_grad()`. `ablation/registry.py` imported 20+ deleted loss classes inside a try/except. Three patterns to audit after any large deletion:
- **Dead code behind early-return**: any `sys.exit(0)` or early return with substantive code below
- **Closure-captured imports**: lambdas or inner functions that capture framework references from their enclosing scope
- **try/except ImportError fallbacks**: registries that silently degrade instead of explicitly handling the deleted module

## Key Decisions

- **No-op deprecation flag, not active rollback**: `--placer jax-deprecated` prints a warning and exits. The actual rollback for a production misroute is "use the previous git tag." The flag exists for one release cycle as a UX placeholder. A/B divergence test required: output with the flag must be byte-different from the default path (see `silent-guard-condition` learning).
- **pyproject.toml JAX removal gated on post-deletion grep**: if any file still imports JAX after the deletion (e.g., geometry/sdf.py, transform.py for autodiff), JAX stays in dependencies with a documented TODO. Full JAX removal is a follow-up.

## Pitfalls

1. **Deleting before relocating shared utilities**: `loss_bridge.py` carried `_resolve_to_indices` used by the SAT bridge. Delete loss_bridge.py first, and the SAT bridge breaks.

2. **Trusting the "22 import wraps" narrative**: The origin doc claimed 22 surviving import wraps needed resolution. Reality: zero try/except ImportError patterns wrapped JAX. JAX was a hard dependency everywhere.

3. **Forgetting pipeline orchestrator modifications**: `pipeline/orchestrator.py:28` had a top-level `import jax.numpy as jnp`. Deleting JAX without modifying the orchestrator breaks `temper pipeline`.

4. **Leaving dead code with broken imports**: ~3,000 lines of dead code survived in `cli/__init__.py` behind `sys.exit(0)`. Static analysis tools (pyright, mypy) flag these as errors even though they're unreachable.

## Files Affected

- `pcl/resolver.py` (new) — `_resolve_to_indices` home
- `core/state.py` — JAX → numpy decoupling
- `cli/__init__.py` — `--placer` flag, `optimize()` cleanup
- `pipeline/orchestrator.py` — JAX removal, CP-SAT dispatch
- `pipeline/stages/refinement_stage.py` — update_fn → no-op
- `pcl/constraints.py` — JAX backend removal, default target change
- `ablation/registry.py` — loss stubs
- `optimizer/`, `losses/`, `placement/`, `loss_bridge.py`, `heuristics/force_directed.py` — deleted (73 files)

## See Also

- `docs/solutions/architecture-patterns/dead-code-deletion-dependency-graph-strangler-2026-06-28.md` — the deletion recipe used as a blueprint
- `docs/solutions/architecture-patterns/pad-position-ssot-placer-2026-06-28.md` — JAX decoupling pattern
- `docs/solutions/workflow-issues/silent-guard-condition-infrastructure-failure-pattern-2026-07-02.md` — A/B divergence test for CLI flags
- `docs/solutions/workflow-issues/silent-source-loss-worktree-parallel-merges-2026-07-01.md` — worktree closure safety checklist
