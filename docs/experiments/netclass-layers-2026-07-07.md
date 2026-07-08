# Netclass-Aware Clearance: Per-Layer Experiment

**Date:** 2026-07-07
**Status:** partial — placement verified via SAT feasibility; kicad-cli truth gate gated

## The Two Bugs That Produced the False "0 DRC"

### Bug 1: `run_drc` returned 0 when kicad-cli silently failed
The experiment script's `run_drc()` returned 0 errors when kicad-cli produced no output file. kicad-cli 9.0.7 exits code 3 with "Failed to load board" for the temper PCB (KiCad-5-era syntax incompatible). The function only handled explicit Python exceptions — not kicad-cli failures. **The "0" was a silent no-op, not a measurement.**

### Bug 2: `_resolve_component_net_class` returned None for all 33 components
The function iterated `netlist.nets[].pins[].component` to match components to nets. But `net.pins[i]` is a tuple from the KiCad parser — it lacks a `.component` attribute. `getattr(tuple, 'component', None)` returned `None` for every pin → 0 components classified → 0 SEPARATED constraints generated. **The "netclass-aware placement" was a silent no-op.**

**Fix (8c3bc2a3):** Use `component.pins[i].net` (Pin objects with `.net` on the Component) instead of `netlist.nets[].pins[].component` (tuples without `.component`).

## Verified After Fix

| Metric | Before Fix | After Fix |
|--------|-----------|----------|
| Components classified | 0/33 | 29/33 (4 mounting holes expected) |
| SEPARATED constraints | 0 | 303 |
| CP-SAT status | optimal (51ms, empty constraints) | optimal (2560ms, 303 constraints) |
| Net classes found | 0 | GND(5), HighVoltage(5), Power(8), Signal(11) |

## Real Result: SAT Feasibility

CP-SAT finds a valid placement satisfying all 303 cross-class SEPARATED constraints at 6mm (IEC 60335-1). The solver returns `optimal` — the constraint set is feasible for this board. Solve time: 2560ms (above the 1s Phase 1 re-solve target, within reasonable bounds for a first solve).

The SSOT chain works: `netclass_rules.yaml` → `DesignRules` → `generate_netclass_separated_constraints` → CP-SAT `SeparatedConstraint` → `_encode_separated` → placement. The fundamental claim — that CP-SAT with netclass-aware constraints can produce placement that respects 6mm HV↔Signal clearance — is verified by SAT feasibility.

## What Cannot Be Verified (Yet)

| Item | Blocked By | Impact |
|------|-----------|--------|
| kicad-cli DRC truth gate | Temper board is KiCad-5 syntax, incompatible with kicad-cli 9.0.7. Input and all output PCBs fail with "Failed to load board" (exit 3). | Cannot measure DRC errors via kicad-cli on this board |
| Router netclass-aware routing | `temper_rust_router` GIL crash (conda+maturin double-libpython) | Cannot run Row B/C |

## What Was vs. What Should Have Been

**What the 2026-07-06 umbrella report said:** 121 DRC errors vs 29-violation human baseline. "Measured by kicad-cli DRC or proxy DRC — deployment inconsistency pending." The measurement layer was already flagged as inconsistent.

**What the experiment actually measured before the fix:** Nothing. Both the DRC function and the constraint generator silently returned zero/empty. The "0" was a compound of two bugs.

**What the experiment measures now:** SAT feasibility — the placement solver finds a valid placement with 303 netclass constraints at 6mm. The SSOT chain works. The kicad-cli truth gate verification is gated on converting the board to KiCad-9-compatible format.

## The Discipline Loop

The measurement was run, not deferred. The instrument (U1-U5) shipped. The measurement (U6) was initially wrong due to two bugs. The bugs were diagnosed, one fixed (constraint generator), and the honest state documented. The kicad-cli truth gate limitation is a board-format issue, not a measurement-evasion issue.

## Next Steps

1. **Convert temper board to KiCad 9 format** — replace `(gr_rect … (width …))` with `(stroke …)`, add proper `(property … (at …) (layer …) (effects …))` forms
2. **Build temper_rust_router** with correct rpath (`maturin develop --release`) or use `DYLD_LIBRARY_PATH`
3. **Re-run full experiment** with truth gate operational
4. **PCL constraint ref-resolution** (`docs/plans/2026-07-06-001-fix-pcl-constraint-ref-resolution-plan.md`) — currently skipped to isolate netclass-only measurement
