---
title: "feat: Finish the Board — 100% Routed, Literal-Zero DRC/ERC"
type: feat
status: active
date: 2026-07-10
origin: docs/brainstorms/2026-07-10-finish-the-board-requirements.md
---

# feat: Finish the Board — 100% Routed, Literal-Zero DRC/ERC

## Summary

Produce one complete temper induction-cooker board: 100% of nets routed and literal-zero DRC/ERC, achieved entirely within the current proven hard-constraint set, with no constraint relaxation or resource padding. The R1 per-net routing diagnosis is already complete — 3/3 unrouted nets have legal paths (routable in isolation), Round 4 of the routing log proves all six critical nets coexist (slack confirmed, not contention), and R3 (placement-topology failure) is off the table. The work is a repaired routing adapter + ordering heuristic, netclass calibration for fine-pitch components, DRC footprint-library-table configuration, and an ERC run + fix, gated by an anti-false-zero guard.

---

## Requirements

Traces to the origin (`docs/brainstorms/2026-07-10-finish-the-board-requirements.md`).

- R1 — **Per-net routing diagnosis** ✅ **already complete.** 3/3 unrouted nets (SPI_MOSI, SPI_CLK, I_SENSE) are individually routable — legal paths exist. Round 4 of the routing log proves all six critical nets (GATE_H, GATE_L, PWM_H, SPI_CLK, SPI_MOSI, I_SENSE) coexist simultaneously — slack confirmed, not contention.
- R2 — Close router-capability failures via ordering heuristic. Route signal nets after power nets so they aren't displaced by later rounds.
- R3 — Close placement-topology failures. **Off the table** — zero nets failed the legal-path-exists test.
- R4 — Netclass calibration: assign fine-pitch nets to `FinePitch` (0.1 mm) so the rule matches the geometry.
- R5 — Configure the DRC gate's footprint library table so `lib_footprint_issues` resolve.
- R6 — ERC to zero.
- R7 — Anti-false-zero guard: completion and zero counts only when measured within the unchanged constraint set against a properly-configured gate, with every closure traceable to R1 diagnosis.

---

## Scope Boundaries

- No constraint relaxation to buy completion. Safety/regulatory hard floors are inviolable.
- No adding layers to dodge diagnosis. The 4th layer is used for a net only when diagnosis proves that net genuinely needs it (no such net was found).
- No footprint rebuild / real-board migration.
- No new sophisticated router before a simpler one is shown to fall short. The ordering heuristic is the simple algorithm; if it fails, escalate to negotiated-congestion only on evidence.

### Deferred to Follow-Up Work

- Negotiated-congestion / PathFinder-style rip-up-reroute — escalate only if the ordering heuristic demonstrably falls short.
- 4th-layer routing for specific nets — escalate only if negotiated-congestion can't fit the region.

---

## Context & Research

### R1 Diagnosis (complete — the foundation for R2)

| Net | Pins | Isolated route? | Round 4 coexistence? | Classification |
|-----|------|-----------------|---------------------|----------------|
| `SPI_MOSI` | 3 | ✅ ROUTED | ✅ coexists with all 5 others | Ordering/displacement |
| `SPI_CLK` | 2 | ✅ ROUTED | ✅ coexists with all 5 others | Ordering/displacement |
| `I_SENSE` | 2 | ✅ ROUTED | ✅ coexists with all 5 others | Ordering/displacement |

**Evidence:** Round 4 of the routing log shows GATE_H, GATE_L, PWM_H, SPI_CLK, SPI_MOSI, I_SENSE all routed simultaneously. The three signal nets route successfully mid-pipeline, then fail in the final round when higher-priority power nets displace them. Slack is proven — ordering, not contention.

**The adapter is broken:** `V6RouterAdapter._build_temp_pcb` exists in the source but isn't registered as a class method (likely a merge artifact from a prior commit). `rrr_route_all_nets` calls `self._build_temp_pcb(...)` which raises `AttributeError`. Repairing the adapter is prerequisite to exposing net ordering — the heuristic has nowhere to live until the adapter can apply an ordering.

### Relevant Code and Patterns

- `packages/temper-placer/src/temper_placer/router_v6/adapter.py` — `V6RouterAdapter` (lines 125+), `rrr_route_all_nets` (line 213), `_build_temp_pcb` (line 318 — broken). The ordering fix lives in `rrr_route_all_nets`: sort `net_order` so signal nets come after power/HV nets.
- `packages/temper-placer/src/temper_placer/router_v6/net_ordering.py` — **does not exist.** The router has no net-ordering module. The ordering is determined by the order nets appear in the netlist or are iterated in `rrr_route_all_nets`. A new `net_ordering.py` module or inline sort in the adapter is the fix.
- `packages/temper-placer/configs/constraints/temper_induction_cooker.yaml` — the constraint set (zones, netclass rules, `SEPARATED`, thermal layout). R4 adds a `FinePitch` netclass (0.1 mm clearance) assigned to the MCU SPI/USB/PWM nets.
- `pcb/temper.kicad_pcb` — the board file. R5 configures the DRC environment to find standard KiCad footprint libraries.
- The Round 4 coexistence proof came from parsing the `✓ NET routed successfully` log lines from `route_pcb` output. A reproducible diagnostic test should capture this pattern.

### Institutional Learnings

- `docs/solutions/logic-errors/weak-nooverlap2d-encoding-allows-zero-gap-2026-07-08.md` — the 121→0 catch. Map-vs-territory: a DRC count that looks good because the gate mis-configures the footprint library is a false zero. R7 is the guard.
- `docs/solutions/architecture-patterns/two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md` — CLEAN/VIOLATIONS/UNMEASURED. The DRC gate must distinguish "checked and clean" from "never checked" — R5 ensures the gate is properly configured.
- `docs/solutions/logic-errors/baseline-extractor-four-silent-fail-metrics-2026-07-01.md` — a gate whose tolerance swallows zero is a false-pass machine. R7: "literal-zero" counts only when the gate is correctly configured.

---

## Key Technical Decisions

- **Ordering heuristic, not negotiated-congestion.** Round 4 proved slack — the cheap branch is the correct one. Escalate only on evidence.
- **Repair the adapter before adding the heuristic.** `_build_temp_pcb` is broken; the fix is mechanical (restore the method binding). The heuristic is then a one-liner sort in `rrr_route_all_nets`.
- **Netclass calibration, not constraint relaxation.** R4 assigns fine-pitch nets to a 0.1 mm clearance rule — the geometry is already correct (the QFN pad pitch is fixed), the rule was just wrong. This is a rule-accuracy fix, not a relaxation.
- **Footprint library table is a gate-config fix, not a board fix.** R5 points `kicad-cli` at the standard libraries so the DRC instrument measures the board correctly.
- **ERC is run-first-then-fix, not guess-then-fix.** R6 starts with a diagnostic ERC run — its output defines the concrete work.

---

## Implementation Units

### U1. Repair the routing adapter + expose net ordering

**Goal:** Restore `V6RouterAdapter._build_temp_pcb` as a working method so `rrr_route_all_nets` can route boards, and add a `net_order` parameter or inline sort so signal nets route after power/HV nets.

**Requirements:** R2

**Dependencies:** None

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/adapter.py` (restore `_build_temp_pcb` method binding; add signal-after-power ordering in `rrr_route_all_nets`)
- Create (if needed): `packages/temper-placer/src/temper_placer/router_v6/net_ordering.py` (simple priority-based net ordering: power/HV nets first, signal nets last)
- Test: `packages/temper-placer/tests/router_v6/test_net_ordering.py`

**Approach:**
- Diagnose why `_build_temp_pcb` is present in the source but not registered as a class method — likely an indentation or merge artifact. Restore the method binding.
- Add ordering: in `rrr_route_all_nets`, sort `net_order` so `SPI_*`, `I_SENSE`, `USB_*`, `TEMP_SENSE` (signal nets) come after `GATE_*`, `PWM_*`, `DC_BUS*`, `AC_*`, `+*V`, `CGND`, `PGND`, `SW_NODE`, `VCC_BOOT` (power/HV nets). The sort key is a simple classification: if net name matches a signal pattern → priority = 99, else priority = 0.
- The Round 4 coexistence proof must be reproducible — add a test that captures the routing log output and asserts all six critical nets appear together in at least one round.

**Test scenarios:**
- Happy: the adapter routes the temper board with the ordering fix and reports ≥ 95% completion (stretch: 100%).
- Regression: Round 4 coexistence — all six critical nets appear together in at least one routing round.
- Edge: the ordering does not degrade completion vs the baseline (87.5%).
- Error: adapter methods are all callable (no AttributeError on `_build_temp_pcb`).

**Verification:** `_build_temp_pcb` is callable; `rrr_route_all_nets` accepts and respects a `net_order` list; signal nets are routed after power nets; the six-net coexistence round is reproducible.

---

### U2. Verify 100% routing on the temper board

**Goal:** Run the ordering-fixed router on the temper board, confirm 100% of nets route, and capture the result as a reproducible artifact.

**Requirements:** R2, R7

**Dependencies:** U1

**Files:**
- No new source files — this unit runs the router and validates the output.
- The routed board artifact is captured for the DRC/ERC gate units (U3/U4).
- Test: `packages/temper-placer/tests/router_v6/test_temper_board_integration.py` (integration — skips if the temper PCB isn't present)

**Approach:**
- Run the adapter with the ordering fix on `pcb/temper.kicad_pcb` at the default placements.
- Assert `completion_rate == 1.0` and `len(unrouted_nets) == 0`.
- If 100% is not achieved, capture which nets remain unrouted and re-run the R1 isolation diagnosis on them — classify whether they are new legal-path-exists failures (ordering not yet tuned) or a new failure class. Do not relax constraints to get the number.
- Write the routed board to a file for downstream DRC/ERC gating.

**Test scenarios:**
- Happy: `route_pcb` returns `completion_rate == 1.0` and `unrouted_nets == []`.
- Integration: the routed board file is valid KiCad s-expression format.

**Verification:** 100% of nets are routed on the temper board within the unchanged constraint set.

---

### U3. Netclass calibration — FinePitch for U_MCU / J_USB

**Goal:** Assign fine-pitch nets to a `FinePitch` netclass (0.1 mm clearance) so the clearance rule matches the actual QFN/connector pad pitch — a rule-accuracy fix, not a relaxation.

**Requirements:** R4

**Dependencies:** None

**Files:**
- Modify: `packages/temper-placer/configs/constraints/temper_induction_cooker.yaml` (add `FinePitch` netclass + per-net assignments)
- Modify (if the netclass loader reads from here): the netclass config authority (check `configs/` or `io/netclass_loader.py`)
- Test: `packages/temper-placer/tests/io/test_netclass_finepitch.py`

**Approach:**
- Identify the nets on U_MCU / J_USB that have fine-pitch pads (SPI, USB, PWM, TEMP_SENSE — check the board's pad definitions or the QFN footprint spec).
- Define `FinePitch` netclass with clearance = 0.1 mm (the QFN pad pitch).
- Assign the identified nets to `FinePitch` in the constraint YAML.
- Verify that `kicad-cli pcb drc` on the routed board with the new netclass shows zero intra-component fine-pitch violations (the ones that were ~22 placement-relevant violations in the baseline).

**Test scenarios:**
- Happy: fine-pitch nets are assigned to `FinePitch` with clearance 0.1 mm.
- Integration: `kicad-cli pcb drc` on a board with these nets reports zero intra-component clearance violations for U_MCU/J_USB pads.
- Edge: non-fine-pitch nets are NOT assigned to `FinePitch` (no accidental over-relaxation).

**Verification:** Fine-pitch intra-component clearances are legal under the calibrated netclass; zero violations for those nets.

---

### U4. DRC footprint library table configuration + ERC to zero

**Goal:** Point `kicad-cli` DRC at the standard KiCad footprint libraries so `lib_footprint_issues` resolve, and run ERC to zero.

**Requirements:** R5, R6

**Dependencies:** U2 (needs the routed board artifact)

**Files:**
- Modify: the DRC gate's footprint library table configuration (check `placer/cp_sat/gates.py` `DrcGate` or the `kicad-cli` invocation in the gate for how library paths are configured). May need a `fp-lib-table` file or `--define` flags.
- Test: `packages/temper-placer/tests/placer/cp_sat/test_drc_gate_config.py` (assert the gate produces CLEAN when footprint libraries are accessible)

**Approach:**
- Identify how the DRC gate invokes `kicad-cli` — examine `DrcGate.check()` for the subprocess call and any `--define` / `--fp-lib-table` flags.
- Configure the standard KiCad footprint library paths so `Capacitor_SMD`, `Package_SO`, `MountingHole`, `Resistor_SMD`, `Package_TO_SOT_SMD`, … are found. The libraries are typically at `/Applications/KiCad/...` or the KiCad system path; the gate must point to them.
- Run ERC on the routed board: `kicad-cli pcb erc pcb/temper.kicad_pcb`. Capture the violation list. Fix ERC violations (likely unconnected pins, missing power flags) within the board file or the checker config.
- Re-run DRC and ERC after fixes; assert literal-zero (0 violations, 0 unconnected items).

**Test scenarios:**
- Happy: `kicad-cli pcb drc` returns 0 violations (including 0 `lib_footprint_issues`).
- Happy: `kicad-cli pcb erc` returns 0 violations.
- Edge: a missing library produces UNMEASURED, not a silent 0-violation pass (R7 anti-false-zero).
- Integration: the DRC gate's `check()` returns `CLEAN` (not `UNMEASURED`, not `VIOLATIONS`).

**Verification:** Literal-zero DRC and ERC on the routed temper board, measured against a properly-configured gate.

---

### U5. Anti-false-zero guard + verification

**Goal:** Enforce R7: "100% routed" and "0 DRC/ERC" count only when measured within the unchanged constraint set against a properly-configured gate, with every unrouted-net closure traceable to the R1 diagnosis.

**Requirements:** R7

**Dependencies:** U2, U3, U4

**Files:**
- Test: `packages/temper-placer/tests/router_v6/test_finish_board_gate.py` (integration: assert the full routed board passes the anti-false-zero checks)

**Approach:**
- Assert the constraint set used for routing is identical to the proven set (no constraint was relaxed — diff the constraint YAML against the baseline).
- Assert the DRC gate's footprint library configuration is present and valid (U4).
- Assert every net that was unrouted in the baseline (SPI_MOSI, SPI_CLK, I_SENSE) is now routed, and the closure is traceable to the R1 diagnosis (ordering — not constraint relaxation).
- Assert the netclass calibration (U3) only affected fine-pitch nets — no non-fine-pitch net was reclassified.

**Test scenarios:**
- Happy: all R7 conditions pass on the completed board.
- Error: a relaxed constraint triggers the guard (constraint diff ≠ baseline).
- Error: a misconfigured DRC gate triggers the guard (library table missing → UNMEASURED, not CLEAN).

**Verification:** The completed board passes all anti-false-zero checks; literal-zero DRC/ERC is measured against a properly-configured gate within the unchanged constraint set.

---

## System-Wide Impact

- **Interaction graph:** U1 (adapter repair) is the prerequisite for routing. U2 (verify 100%) depends on U1. U3 (netclass) and U4 (DRC/ERC) are independent of U1/U2 but both depend on U2's routed board artifact. U5 (anti-false-zero) depends on U2/U3/U4.
- **Behavior changes:** the adapter repair (U1) restores a broken method — no functional change to existing callers. The ordering heuristic changes which nets route first but does not alter the constraint set or the routing algorithm.
- **Error propagation:** the DRC gate's configuration (U4) must produce UNMEASURED when libraries are missing, not a silent zero — same fail-closed discipline as every other gate.
- **Unchanged invariants:** the proven hard-constraint set (netclass SEPARATED, courtyard, edge margin, creepage) is unchanged. R3 (placement-topology feedback) is off the table.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Ordering fix doesn't achieve 100% | Re-run R1 isolation diagnosis on any remaining unrouted nets — classify and escalate only on evidence (negotiated-congestion then 4th layer) |
| Adapter repair uncovers deeper breakage | `_build_temp_pcb` is a ~25-line method — the fix is mechanical. If the adapter has broader breakage, revert to the working `route_pcb` path and inject ordering through the pipeline |
| Footprint library table not portable across machines | Use KiCad system environment variables (`KICAD7_FOOTPRINT_DIR`) or a project-local `fp-lib-table`; CI must be configured consistently |
| ERC reveals systemic netlist issues (not just config) | ERC is diagnostic-first — scope adapts to what the run finds; file follow-up tickets for anything beyond config/power-flag fixes |

---

## Success Metrics

- **100% of nets routed** on the temper board, within the unchanged constraint set.
- **Literal-zero DRC and ERC**, measured against a properly-configured `kicad-cli` gate.
- Every unrouted-net closure traceable to R1 diagnosis (ordering/displacement — no constraint relaxation, no resource padding, no added layers).
- The anti-false-zero guard (R7) passes: the completed board's constraint set matches the baseline, the gate is properly configured, and zero was not bought by weakening the problem.

---

## Sources & References

- **Origin document:** [docs/brainstorms/2026-07-10-finish-the-board-requirements.md](docs/brainstorms/2026-07-10-finish-the-board-requirements.md)
- **R1 diagnosis evidence:** Round 4 coexistence (GATE_H, GATE_L, PWM_H, SPI_CLK, SPI_MOSI, I_SENSE all routed simultaneously); per-net isolation test (3/3 SPI nets routable individually).
- **Key code:** `packages/temper-placer/src/temper_placer/router_v6/adapter.py`, `packages/temper-placer/configs/constraints/temper_induction_cooker.yaml`, `pcb/temper.kicad_pcb`
- **Key learnings:** `docs/solutions/logic-errors/weak-nooverlap2d-encoding-allows-zero-gap-2026-07-08.md`, `docs/solutions/architecture-patterns/two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md`
