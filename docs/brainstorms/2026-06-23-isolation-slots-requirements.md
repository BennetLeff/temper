---
date: 2026-06-23
topic: isolation-slots-in-slot-generation
focus: Consume existing `isolation_slots` config in slot generation and propagate effective creepage reduction to DRC oracle
origin: docs/ideation/2026-06-23-hv-clearance-placement-completion-ideation.md (idea #7)
status: draft
actors: zone_aware_slot_generation, DRC oracle, kicad writer, config loader
---

# Requirements: Consume Existing Isolation Slots in Slot Generation

## Problem Frame

The deterministic PCB routing pipeline completes only 33% of nets (8/24) before hitting a wall: 10 nets are blocked by 6mm HV creepage clearances around TO-247 power components Q1, Q2, D1, D2. The creepage requirement derives from IEC 60335-1 / IEC 62368-1 Annex G: surface distance between gate (LV) and collector (HV) pins must be ≥ 6mm.

`configs/temper_deterministic_config.yaml:482-499` already declares `isolation_slots` — 1.5mm wide milled cutouts positioned at `(2.725, -5.0) → (2.725, 5.0)` relative to each TO-247 component origin. These cutouts force the creepage path to detour around the slot, achieving 12-15mm effective creepage even though the through-air distance is only 5.45mm. The geometry is the canonical mitigation described in the config's own comment block (lines 470-481).

The data path is broken in two places:

1. **`packages/temper-placer/src/temper_placer/deterministic/__init__.py:55-180` never extracts `isolation_slots` from the loaded `Constraints` object.** `Constraints.isolation_slots` is populated by `io/config_loader.py:1304-1319` and the config parser at `:1366` registers the key, but the deterministic module's config-extraction block (which already reads `copper_zones`, `slot_generation`, `net_class_rules`, `hv_exclusion_zones`) does not pull the list. The data is loaded then dropped.

2. **`packages/temper-placer/src/temper_placer/deterministic/stages/zone_aware_slot_generation.py:169-229` filters slots against copper pour polygons only.** `_is_slot_in_copper_zone` (lines 231-288) walks the copper zone list and discards slots that fall inside a copper polygon. It has no concept of a milled isolation cutout as a slot-blocker, and it has no mechanism to communicate to the DRC oracle that an isolation slot relaxes clearance requirements.

The `io/kicad_writer.py:1132-1189` path does consume `isolation_slots` for output, and `tests/io/test_isolation_slots.py` exercises that path. The gap is exclusively in the slot-generation → DRC-oracle seam.

The expected payoff: ~4mm of reclaimed routing channel per Q1/Q2 slot (the slot collapses the 6mm clearance to ~2mm of forbidden area on either side of the cutout, freeing the middle of the channel for traces).

**Net-attribution mapping** (of the 10 stuck nets): 7 are Q1↔Q2 source/sink pairs (in scope), 2 are Q1↔D1 cross-net (handled by Q1's slot), 1 is D1↔D2 (out of scope, deferred).

## Actors

- **A1. `DeterministicPipeline` builder** — assembles the stage DAG in `deterministic/__init__.py`. Must thread `isolation_slots` from `Constraints` into `ZoneAwareSlotGenerationStage` (mirroring the existing `yaml_copper_zones` pattern at line 79, 171).
- **A2. `ZoneAwareSlotGenerationStage`** — currently filters slots against copper pour polygons. Must additionally treat isolation slot cutouts as slot-blockers and emit the effective clearance reduction downstream.
- **A3. `DRCOracle`** — `routing/constraints/drc_oracle.py` validates clearance against `ClearanceMatrix` and applies `INTERNAL_LAYER_CREEPAGE_FACTOR=0.30` for internal layers. Must accept a per-component creepage credit when a slot sits between the gate and HV pin.
- **A4. Router stages** — consume DRC oracle verdicts. Indirect beneficiary: a more accurate oracle permits routing through reclaimed channels that would otherwise be blocked by a 6mm exclusion.
- **A5. `kicad_writer.add_isolation_slots_to_pcb`** — already serializes the slots into the `.kicad_pcb` output. No change required; correct round-trip is the validation signal that the slot data was preserved end-to-end.

## Key Decisions

- **K1. Reuse, do not invent.** The slots are already declared in config. The only new code is the seam that reads them and the two new behaviors (slot-blocking + clearance credit). Zero new config keys, zero new top-level data structures.
- **K2. Isolation slots are slot-blockers, not zone-blockers.** Unlike copper pour polygons (which are continuous regions slots must avoid), an isolation slot is itself a milled cutout. Slots in the placer must not be placed on top of it (it would create redundant milling). Treat isolation slot rectangles the same way `_is_slot_in_copper_zone` treats copper polygons: a point-in-rectangle containment test against the slot's footprint, expanded by the slot's `width_mm`.
- **K3. Clearance credit is per-pin-pair, not global.** The config already names the `lv_pin` and `hv_pin` for each slot. The credit applies only to clearance checks between those two specific pins. Other HV pairs (D1/D2, transformer secondaries) are unaffected. This preserves the conservative default for the rest of the board.
- **K4. Reclaim amount derives from config comment, not invented math.** The config comment at lines 470-481 states the slot achieves "12-15mm effective" creepage. The credit to the DRC oracle is computed as:

    ```
    reclaim = clamp(slot.width_mm / 2 + perpendicular_clearance_budget - 5.45mm,
                    0,
                    original_requirement - 0.5mm)
    new_requirement = max(0.5mm, original_requirement - reclaim)
    ```

    Worked example for Q1: `original_requirement = 6mm`, `slot.width_mm = 1.5mm`, `perpendicular_clearance_budget = 5.5mm` (the conservative lower bound of the 5-6mm band reserved for the perpendicular axis). Then `reclaim = clamp(0.75 + 5.5 - 5.45, 0, 5.5) = clamp(0.8, 0, 5.5) = 0.8mm`. So `new_requirement = max(0.5, 6.0 - 0.8) = 5.2mm`. The DRC oracle accepts any Q1 gate↔collector clearance ≥ 5.2mm within the slot's reclaimed band (R3), and ≥ 6.0mm everywhere else.
- **K5. Do not touch the internal-layer creepage factor.** `INTERNAL_LAYER_CREEPAGE_FACTOR=0.30` (line 71) and `INTERNAL_LAYERS` (line 60) address a different relaxation pathway (plane shielding). Isolation-slot credit stacks multiplicatively with internal-layer credit: a route under a plane through a slot-region gets both reductions.

## Requirements

### R1. Extract `isolation_slots` from Constraints in the deterministic module
Status: required

`packages/temper-placer/src/temper_placer/deterministic/__init__.py` (around line 67) gains a new local `yaml_isolation_slots = []` initialized alongside the other config-derived lists. The config-extraction block (lines 75-180) adds a branch that reads `getattr(config, "isolation_slots", [])` and passes it as a new keyword argument `yaml_isolation_slots=yaml_isolation_slots` to the `ZoneAwareSlotGenerationStage` constructor (line 171 region, alongside `yaml_copper_zones=yaml_copper_zones`).

Acceptance: the value passed to the stage is the same `list[IsolationSlot]` that `io/config_loader.py:1304-1319` populates, with all original fields preserved (`name`, `component_ref`, `start_offset`, `end_offset`, `width_mm`, `lv_pin`, `hv_pin`).

### R2. Treat isolation slots as slot-blockers
Status: required

A candidate slot whose footprint intersects any isolation-slot cutout (computed in board coordinates from the cutout's component-local offsets and that component's current position) is rejected.

### R3. Propagate effective clearance reduction to DRC oracle
Status: required

The DRC oracle accepts, keyed by `(component_ref, pin_a, pin_b)`, a clearance reduction applicable only to clearance checks between those pins. The reduction is spatially scoped to the slot's reclaimed band, defined precisely as: the credit applies if and only if the line segment between the two pad centers intersects the slot's axis-aligned bounding rectangle, expanded on each side by `max(slot.width_mm / 2, 0.5mm)`. Endpoints outside the expanded rectangle receive no credit. Pin pairs whose owning `component_ref` differs from the slot's `component_ref` receive no credit.

### R4. Round-trip preservation via kicad_writer
Status: required

No change to `io/kicad_writer.py:1132-1189`, but the existing `tests/io/test_isolation_slots.py` fixtures must still pass end-to-end: the slot declared in YAML appears in the output `.kicad_pcb` file. This is the regression guard against the seam accidentally mutating or dropping the slot data.

### R5. Test coverage for the seam
Status: required

A new test file under `packages/temper-placer/tests/deterministic/` exercises:
- R1: `Constraints` with the existing YAML isolation_slots section is loaded, the deterministic module extracts the list, the value passed to the stage equals the loaded value.
- R2: a stage run with Q1/Q2 isolation slots emits zero slots overlapping the cutout rectangles, but emits slots in the surrounding routing channel.
- R3: the DRC oracle, given a clearance credit record for `(Q1, 1, 2)`, accepts a trace at the credit-reduced clearance when both endpoints are near the slot axis, and rejects the same trace when the endpoints are far from the slot.
- End-to-end: the routed completion rate on the 24-net test board improves from 33% toward 100%, with the 10 previously-stuck nets now passing at the credit-reduced clearance.

### R6. Logging and observability
Status: required

The stage's existing `logger.info` block (lines 224-227) is extended to report how many slots were filtered by copper zones vs. by isolation slots, separately. A second log line reports the total clearance reclaim: `f"Isolation slots reclaim {total_reclaim_mm:.2f}mm of routing channel"`. This is the diagnostic signal that the change is active and producing the expected effect.

## Out of Scope

- Adding new isolation slot entries to the YAML config. The existing Q1/Q2 entries are sufficient to validate the seam.
- Changing `INTERNAL_LAYER_CREEPAGE_FACTOR` or `INTERNAL_LAYERS`. The slot credit stacks with the internal-layer factor, not replaces it.
- Adding isolation slots for D1/D2 or transformer secondaries. Those nets are not in the 10-net stuck list; defer until the seam is proven on Q1/Q2.
- Modifying `io/kicad_writer.add_isolation_slots_to_pcb`. The output path is already correct; touching it risks breaking the round-trip guard.
- Geometric computation of optimal slot position per component. The config-declared position is treated as ground truth.

## Success Criteria

- Routed net count reaches 23/24 on the closure test board at the three seeds listed in `docs/test-boards/closure-seeds.txt` (currently passing 8/24), and the 10 nets previously blocked by Q1/Q2 6mm creepage (enumerated in the new `tests/deterministic/test_isolation_slots_in_slot_generation.py` fixture) all complete at every seed.
- Zero DRC violations introduced (the 10 previously-stuck nets must pass cleanly, not by relaxation that allows a new violation).
- `tests/io/test_isolation_slots.py` continues to pass unchanged.
- The new `tests/deterministic/test_isolation_slots_in_slot_generation.py` passes for R1, R2, R3, and the end-to-end routing scenario.
- Code added is ≤ 40 lines net (matches the ideation doc's complexity estimate) excluding tests.

## See Also

- Ideation source: `docs/ideation/2026-06-23-hv-clearance-placement-completion-ideation.md` (idea #7, axis: zone topology surgery / HV footprint inflation)
- Roadmap position: #6 of 7 in the recommended execution order — runs after ghost-pad injection (#2) and seed filtering (#4) so the placer already understands HV exclusion before the slot credit relaxes it.
- Per-stage DRC fence: `docs/brainstorms/2026-06-22-per-stage-drc-fence-requirements.md` — the fence pattern from that brainstorm will catch any R3 violation where the credit is applied outside the slot's spatial scope.
- Internal-layer creepage rationale: `drc_oracle.py:62-71` (K5 cross-reference)
