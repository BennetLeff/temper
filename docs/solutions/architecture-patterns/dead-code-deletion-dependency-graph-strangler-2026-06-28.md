---
module: temper_placer
date: "2026-06-28"
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - "When deprecating a large module or directory that still has active consumers scattered across the codebase"
  - "When you need to safely remove thousands of lines of dead code spread across interdependent files"
  - "When migrating infrastructure (routers, APIs, frameworks) with many dependent modules that must be ported incrementally"
  - "When a legacy implementation lives alongside its replacement and the doubling of maintenance burden must be resolved"
symptoms:
  - "Legacy module sits next to its replacement, causing confusion about which implementation to use"
  - "Manual effort required to determine which files are safe to delete and which still have active importers"
  - "Large deletions in single PRs risk merge conflicts and hard-to-review diffs"
root_cause: missing_tooling
resolution_type: workflow_improvement
tags:
  - dead-code-removal
  - dependency-graph
  - progressive-strangler
  - large-scale-cleanup
  - code-migration
  - deprecation
  - router-migration
  - architecture-pattern
---

# Dead Code Deletion Via Dependency Graph Analysis + Progressive Strangler

## Context

The temper-placer codebase had two coexisting PCB routers: `router_v6/` (modern, ~16K lines) and `routing/maze_router` (legacy, ~5K lines). After the `router_v6` closure rate reached 100%, the legacy routing subsystem was pure dead weight — dual imports, split maintenance, and architectural ambiguity about which router was canonical. The `routing/` directory totaled ~26K lines across 66 files. A naive deletion would break 30 external consumers spread across 17 modules. The solution: dependency-graph-driven progressive deletion across 17 atomic PRs.

## Guidance

### Step 1: Build the import dependency graph

Before deleting anything, compute the full import graph:

```bash
# Find every external file that imports from the target directory
rg "from temper_placer\.routing\." packages/ -l

# Find internal import edges within the target directory
rg "from temper_placer\.routing\." packages/temper-placer/src/temper_placer/routing/ -l
```

From this, construct the graph:
- **Nodes**: all files in the target directory
- **Edges**: directed imports (A imports from B → edge A→B)
- **Live roots**: files imported by code outside the target directory
- **Transitive closure**: BFS from live roots to find all reachable files

Files unreachable from live roots are dead code — safe to delete immediately. Files reachable are either leaf utilities (useful, should be moved) or the core router (delete last).

### Step 2: Determine deletion order

Delete in reverse-topological order — files nothing depends on first, core last:

1. **Zero-ref leaf files** — delete immediately (no imports from anywhere)
2. **Support files** — constants, standalone helpers with no internal dependents
3. **Verifier / metrics / analysis** — easy to port to new router's output format
4. **Leaf utilities imported externally** — move to the replacement module, update import paths
5. **Core router** — delete last, once zero consumers remain

### Step 3: Build an adapter for consumer porting

Before consumers can switch, build an adapter matching the legacy interface but delegating to the replacement:

```python
class V6RouterAdapter:
    """Exposes MazeRouter.from_board() + rrr_route_all_nets()
    but delegates to RouterV6Pipeline internally."""

    @classmethod
    def from_board(cls, board, cell_size_mm, num_layers, design_rules):
        return cls(board=board, ...)

    def rrr_route_all_nets(self, netlist, positions, net_order, assignments):
        return self._pipeline.run(...)
```

The adapter makes consumer porting mechanical — an import-path change, not a logic rewrite.

### Step 4: Port consumers and move leaf utilities

For each external consumer:
1. Change the import path to the new location
2. Verify tests pass
3. Delete the old file once zero imports remain

For useful leaf utilities (net_ordering, layer_assignment, etc.):
1. `cp` or `git mv` to the replacement module
2. Update all external imports to the new location
3. Delete the original

### Step 5: Final consolidation

After all consumers are ported and all leaf utilities moved:

```bash
# Verify zero external imports remain
rg "from temper_placer\.routing\." packages/ -l --glob='!routing/*'
# Expected: empty

# Delete the entire directory
git rm -r packages/temper-placer/src/temper_placer/routing/
```

Clean up stale import-linter contracts, allowlist entries, and manifest references.

### Tooling

| Tool | Purpose |
|------|---------|
| `rg "from temper_placer\.routing\."` | Find all external/internal imports |
| Python BFS from live roots | Compute transitive closure |
| `git mv` | Move leaf utilities preserving history |
| `scripts/import_linter_gate.py` | Verify no import boundary violations |

## Why This Matters

**Single routing strategy.** Before, two routers coexisted causing ambiguity about which to use, extend, or debug. After, `router_v6/` is the single canonical routing engine.

**Reduced maintenance surface.** 26K lines of dead code removed. Every grep, IDE search, and import analysis no longer returns false positives from the vestigial directory.

**Architectural clarity.** The import-linter boundary contracts were simplified — no more exemptions for routing shims.

**Precision over bulk deletion.** A naive `rm -rf` would have broken 30 consumers. The dependency-graph approach identified exactly which files were dead, which were worth keeping, and which consumers needed porting — enabling 17 atomic PRs that each passed CI.

## When to Apply

- Two implementations coexist and the replacement is production-verified
- The old directory is large (>20 files, >3K lines)
- Consumers are spread across multiple modules
- The replacement has a compatible or adaptable interface
- CI provides a safety net for each incremental deletion

Do NOT apply when the old code is small (<10 files), the replacement lacks required features, or consumer porting requires full rewrites rather than mechanical import-path changes.

## Examples

**Before:** `routing/` (66 files, 26K lines) lived alongside `router_v6/` (80 files, 16K lines). 30 files imported from `routing/`. `rg "MazeRouter"` returned hits in both directories.

**After:** `routing/` deleted entirely. `router_v6/` holds all routing functionality including migrated leaf utilities (net_ordering, layer_assignment, grid_converter, path_simplify, serpentine, congestion, verifier, constraints types). Zero external imports reference the old path.

**Consumer porting (mechanical change):**
```python
# Before
from temper_placer.routing.maze_router import MazeRouter
router = MazeRouter.from_board(board, cell_size_mm=0.5, num_layers=2, design_rules=dr)

# After
from temper_placer.router_v6.adapter import V6RouterAdapter
router = V6RouterAdapter.from_board(board, cell_size_mm=0.5, num_layers=2, design_rules=dr)
```

**Commit sequence (17 PRs, one session):**
1. Build V6RouterAdapter in `router_v6/adapter.py`
2-3. Port consumers batch 1-2 (auto_layout, internal_route, pipeline files)
4-5. Delete dead routing modules (zero-ref, transitively dead)
6-7. Move leaf utilities to router_v6/
8-9. Move congestion/verifier/constraints types
10. Delete routing/ directory, move to _routing_shim
11. Consolidate _routing_shim, delete duplicates
12. Clean up CI gates (import-linter, allowlist)
13. Clean up docs (obsolete routing/ docs)
14-15. Post-cleanup (dead losses, stale PCBs, simulation artifacts)
16-17. Final fixups (broken imports, serpentine DiffPairPath)

Total: ~55K lines deleted, ~10K lines moved, 17 atomic PRs merged.

## Related

- `docs/solutions/architecture-patterns/strangler-fig-pipeline-decomposition-2026-06-22.md` — Strangler fig pattern establishing the adapter architecture
- `docs/solutions/architecture-patterns/v5-astar-migration-path-2026-06-24.md` — Prior V5→V6 migration using same dependency-graph approach
- `docs/solutions/tooling-decisions/import-linter-boundary-enforcement-ratchet-2026-06-22.md` — Import boundary enforcement (ratchets prevent re-coupling)
- `docs/solutions/architecture-patterns/ci-gate-quality-enforcement.md` — Dead-code gate (Vulture monotonic shrink) and consolidation guard pattern
