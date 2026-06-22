---
date: 2026-06-21
topic: clean-base-sprint
status: ready-for-planning
---

# Requirements: Temper Clean Base Sprint

## Goal

An agent picking up the Temper repo cannot silently re-introduce schematic P0 bugs or produce PCB work that violates electrical safety rules. All three enforcement layers (atopile build, KiCad DRC, Python DRC runner) are complete, consistent, and derived from a single source of truth.

## Problem

The project has three enforcement layers that are all partially built but none fully wired:

| Layer | Current state | Gap |
|---|---|---|
| Atopile (schematic) | 2/6 P0 bugs have assertions | 4 bugs unguarded; `ato compile` passes broken schematics |
| KiCad DRC (`.kicad_dru`) | 144-line hand-authored file | Drifting from `design_rules.py` and `temper.kicad_pro`; 3 sources |
| Python DRC runner | 11 checks implemented, 2 missing | `checks/__init__.py` exports nothing; runner never fires |

Each layer can be bypassed independently. An agent that works in KiCad directly bypasses atopile. An agent that skips KiCad DRC bypasses `.kicad_dru`. An agent that doesn't call the Python runner bypasses the implemented checks. Six months of routing work on a schematic with an LMR51430 fed at 340V (rated 36V) demonstrates the cost.

## Success Criteria

1. `ato compile` fails when any of the 6 P0 schematic conditions is violated — no agent session can leave P0 bugs in place without a visible build failure
2. `python -m temper_drc` (or `uv run temper-drc`) produces a structured violation report against the KiCad board file — the runner works, names violations, and references the net class that was violated
3. `pcb/temper.kicad_dru` is auto-generated from `packages/temper-placer/temper_placer/core/design_rules.py` by a build script — the hand-authored file is replaced; discrepancies between the three sources are resolved in `design_rules.py`
4. `CLAUDE.md` encodes the schematic-first sprint gate: no routing session begins until `ato compile` passes clean

## Scope

### In Scope

**Workstream 1 — Atopile assertions for remaining P0 bugs**

Six P0 bugs documented in `SCHEMATIC_AUDIT_REPORT.md`. Two already have assertions or are stale (Bug 3 cap value assertion may exist in `elec/src/modules.ato`; Bug 2's PowerManagement module is no longer instantiated in Top). The remaining bugs needing new assertions:

- LMR51430 supply voltage: assert input voltage ≤ 36V (LMR51430 absolute max); currently wired at 340V DC bus
- HV rail connectivity: assert HV rail is wired to power management block (structural module-level check)
- No EMI filter: assert EMI filter module is instantiated in Top
- No pan detection: assert pan detection module is instantiated in Top

For connectivity/instantiation assertions that atopile's value-range `assert` syntax cannot express natively, add structural checks as `assert` blocks in the relevant module's `__init__` or add a build-time Python validation script that `ato build` calls as a post-hook.

**Workstream 2 — `temper_drc` runner factory**

File: `packages/temper-drc/temper_drc/checks/__init__.py` — currently contains only `"""${dir} module."""`.

Tasks:
- Import and re-export all 11 existing check implementations (ClearanceCheck, HVLVSeparationCheck, CreepageCheck, LoopAreaCheck, and others in `packages/temper-drc/temper_drc/checks/`)
- Implement `TraceWidthCheck` — verifies each trace width against its net class minimum from `TEMPER_NET_CLASSES`
- Implement `LayerAssignmentCheck` — verifies HV nets (DC_BUS+, DC_BUS-, SW_NODE) route on B.Cu (L4), gate nets on F.Cu (L1)
- Implement a `create_temper_checks()` factory function that instantiates all 13 checks with `TEMPER_NET_CLASSES` as the constraint source
- Implement a `__main__.py` entry point: `python -m temper_drc <path/to/board.kicad_pcb>` runs all checks and prints structured results

All existing checks must be parameterized from `TEMPER_NET_CLASSES` in `packages/temper-placer/temper_placer/core/design_rules.py` — no hardcoded values in check implementations.

**Workstream 3 — `.kicad_dru` generation script**

Current state: `pcb/temper.kicad_dru` is 144 lines, hand-authored, and drifting from `design_rules.py` (e.g., Ground clearance: 0.2mm in kicad_dru vs 0.3mm in design_rules.py).

Tasks:
- Audit the three sources (`design_rules.py`, `temper.kicad_dru`, `temper.kicad_pro`) for discrepancies — resolve all discrepancies by updating `design_rules.py` as authoritative
- Write `scripts/generate_kicad_dru.py` that reads `TEMPER_NET_CLASSES` and writes `pcb/temper.kicad_dru` in KiCad Design Rules format
- Replace the current hand-authored `temper.kicad_dru` with the generated output
- Add `generate_kicad_dru.py` to the project's build/setup instructions so it can be re-run whenever `design_rules.py` changes
- Net class → KiCad net name mapping: use `TEMPER_NET_ASSIGNMENTS` in `design_rules.py` (already maps net names to classes)

**Workstream 4 — CLAUDE.md schematic-first gate**

Add a mandatory process rule to `CLAUDE.md`: no routing session begins until `ato compile` passes with zero errors. Include the exact command. Encode this as a numbered step in the agent workflow, not an advisory note.

### Out of Scope

- Board-specific routing script — separate workstream, depends on this sprint completing first
- DESAT schematic implementation — a P0 hardware gap requiring schematic work; covered in parallel
- Gerber export / board order — downstream of schematic correctness; unblocked by this sprint
- Pan detection circuit design — hardware gap, separate session
- EMI filter circuit design — hardware gap, separate session
- Firmware changes — no PCB work required

## Dependencies and Risks

**Atopile assertion expressiveness**: Atopile's `assert` syntax handles value-range checks well (confirmed in `elec/src/main.ato`). Structural connectivity assertions ("HV rail must be wired to power management") may require `assert module.component != None` or similar — verify atopile's assertion grammar supports this before writing. Fallback: a Python build-time script called from a Makefile target.

**`.kicad_dru` drift resolution**: When `design_rules.py` and `temper.kicad_dru` disagree, the correct value must be determined from first principles (datasheet, IPC-2221 creepage tables, etc.) before `design_rules.py` is updated. Do not silently pick one — each discrepancy is a potential safety issue.

**Existing check assumptions**: The 11 implemented checks may have hardcoded values that don't match `TEMPER_NET_CLASSES`. Audit each check's constraint source during Workstream 2 rather than assuming they're already parameterized.

**DESAT module in modules.ato**: Workstream 1's "assert EMI filter module instantiated" / "assert pan detection module instantiated" assertions will immediately fail `ato compile` because those modules don't exist yet. These assertions should be written as `assert False, "EMI filter module missing — add DesatProtection, EMI, PanDetection modules before routing"` or written after the modules are added. Coordinate timing with the hardware gaps session.

## Single Source of Truth

After this sprint, `packages/temper-placer/temper_placer/core/design_rules.py` is the authoritative source for all electrical rules. All other files derive from it:

```
design_rules.py (TEMPER_NET_CLASSES + TEMPER_NET_ASSIGNMENTS)
    ↓ generate_kicad_dru.py
pcb/temper.kicad_dru  → KiCad DRC uses this
    ↓ create_temper_checks()
temper_drc runner     → Python DRC uses this
    ↓ ato compile
atopile assertions    → Schematic build uses these
```

Any rule change requires updating `design_rules.py` only; the rest regenerates or re-imports.
