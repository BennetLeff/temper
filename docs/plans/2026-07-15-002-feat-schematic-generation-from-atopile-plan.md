---
title: "feat: Generated KiCad schematics from Atopile netlist"
type: feat
status: completed
date: 2026-07-15
origin: docs/brainstorms/2026-07-15-generated-kicad-schematics-from-atopile-requirements.md
---

# feat: Generated KiCad schematics from Atopile netlist

## Summary

Close the #1 pipeline gap: `elec/src/*.ato` -> `elec/build/default.net` -> **`pcb/*.kicad_sch`** (currently unbuilt). A script generates all 7 hierarchical sheets from the atopile netlist using synthesized box symbols and pure label-per-pin connectivity. A built-in oracle verifies connectivity partition isomorphism against the source netlist. This unblocks production-board creation and the artifact identity system.

---

## Problem

```
elec/src/*.ato --[ato build (working)]--> elec/build/default.net (100 comps, 135 nets, 0 unconnected)
                                            |
                                +===========+===========+
                                |  GAP -- nothing generates  |
                                |  pcb/*.kicad_sch from this |
                                +===========+===========+
                                            |
pcb/*.kicad_sch (hand-drawn, 120 unconnected pins, 215 ERC violations, backwards IGBTs)
```

After this plan ships:

```
elec/build/default.net --[gen_schematics.py]--> pcb/*.kicad_sch (generated, oracle-verified)
                                                      |
                                            [kicad-cli sch export netlist]
                                                      |
                                            connectivity partition diff --> PASS/FAIL
```

---

## Key Technical Decisions

### Symbol source: synthesize all as boxes

**Decision: synthesize ALL symbols as simple rectangles with numeric pin labels.** Even ICs with local `.kicad_sym` files get synthesized boxes. Why:

- Schematics are **not a review artifact** (review happens in `.ato`). They exist only for netlist export -> PCB sync.
- Synthesized boxes are total over any new component added to `.ato` -- no manual symbol-harvesting step ever needed.
- The oracle verifies connectivity is correct regardless of symbol aesthetics.
- This eliminates the symbol-mapping problem entirely: no MPN->symbol lookup, no library path resolution, no pin-name-to-number translation.

If readable schematics are needed later (for manufacturing review), revisit with harvested symbols as a cosmetic pass. Cosmetics must not gate pipeline correctness.

The netlist has 100 components across 19 atopile types. All are synthesized from `libparts` pin counts:

| Category | Count |
|---|---|
| Passives (Resistor, Capacitor, CapPolarized, Inductor, Diode, Fuse, NTC_Inrush) | ~73 |
| ICs with local `.kicad_sym` (IKW40N120H3, UCC21550, ESP32-S3, XC6220, MAX31865, SN74HC4075) | ~20 |
| Simple semis (MOSFET_N, MUR1560, TestPoint, CST1005, Relay_SPST, LMR51430) | ~7 |

### Connectivity: pure label-per-pin

Every pin gets a net label at its absolute endpoint. No wires anywhere. This eliminates the entire wire-geometry bug class that caused every historical safety bug.

### Module-to-sheet mapping

Derived from `sheetpath.names` in the netlist:

| Module prefix | Sheet | Components |
|---|---|---|
| `power_in` | Power_Input | 14 |
| `hb` | Half_Bridge | 15 |
| `power_mgmt` | Power_Management | 11 |
| `safety` | Safety_Interlock | 20 |
| `ct_sense` | Safety_Interlock (merged) | 3 |
| `rtd_pan` | Sensing | 29 |
| `mcu` | MCU | 5 |
| `tank` | Half_Bridge (merged) | 3 |

**Decisions:**
- `ct_sense` (3 components) merges into Safety_Interlock -- functionally part of the safety interlock chain, too small for its own sheet.
- `tank` (3 components: resonant coil + caps) merges into Half_Bridge -- the tank is the load of the half-bridge output. User_Interface is reserved for actual UI components (buttons, LEDs, display) that don't exist yet in atopile.

This produces **6 sub-sheets** (not 8): Power_Input, Half_Bridge, Power_Management, Safety_Interlock, Sensing, MCU.

---

## Implementation Phases

### Phase 1 -- Symbol Synthesizer + Netlist Parser

#### [NEW] scripts/gen_schematics.py (main entry point)

```
Usage:
    python scripts/gen_schematics.py [--check] [--netlist PATH] [--output-dir PATH]

Modes:
    (default)   Generate schematics and verify via oracle
    --check     Verify existing schematics match netlist (CI mode)
```

Core modules within the script:

**netlist_parser.py** -- Parse `default.net` S-expressions (reuse pattern from `real_board_inventory.py`'s `_sexp()` parser):
- Extract all components with ref, footprint, part, description, sheetpath, tstamps
- Extract all nets with code, name, and node list (ref, pin)
- Extract libparts with pin counts per part
- Validate: 100 components, 135 nets, no duplicates

**symbol_synthesizer.py** -- Generate box symbols from libparts:

```python
def synthesize_symbol(part_name: str, pin_count: int, pin_names: list[str]) -> str:
    """Return KiCad S-expression for a rectangular box symbol.

    Pins placed vertically along left/right edges.
    Left side: pins 1..N//2, Right side: pins N//2+1..N.
    For 2-pin parts: pin 1 left, pin 2 right.
    """
```

**sheet_generator.py** -- Emit `.kicad_sch` files:
- Grid placement: components in rows, 20mm spacing, grouped by sub-module
- Net labels at every pin endpoint (computed from symbol origin + pin offset)
- Hierarchical labels for inter-sheet nets
- Stable UUIDs derived from atopile tstamps (deterministic)
- `GENERATED -- do not hand-edit` header comment

**oracle.py** -- Post-generation verification (built into gen_schematics.py, runs automatically):
- Run `kicad-cli sch export netlist` on generated project
- Parse both netlists (generated export and original `default.net`)
- Compare **connectivity partitions**: group `(ref, pin)` pairs by net, ignoring net names
- Report any mismatch as: which pins are in the wrong group
- Also check: zero unexpected `unconnected-(...)` nets

---

### Phase 2 -- Sheet Assembly

#### [OVERWRITE] pcb/temper.kicad_sch (root)

Generated root schematic containing:
- 6 sheet instance blocks (one per sub-sheet)
- Hierarchical pins on each sheet block matching the inter-sheet nets
- Net labels at every hierarchical pin endpoint (no wires between sheets)
- `lib_symbols` section with all synthesized symbols
- Project UUID derived from atopile build

#### [OVERWRITE] pcb/{power_input,half_bridge,power_management,safety_interlock,sensing,mcu}.kicad_sch

Each sub-sheet generated with:
- Components from the corresponding atopile module(s)
- Synthesized box symbols in `lib_symbols`
- Grid placement (row-major, grouped by sub-module path depth)
- Net label at every pin
- Hierarchical labels for nets that cross sheet boundaries
- No-connect markers on pins that appear in components but are not connected to any multi-node net

---

### Phase 3 -- Oracle & CI

#### [NEW] CI step (regen-and-diff pattern)

In `.github/workflows/schematic-check.yml` (or existing `python-tests.yml`):

```yaml
- name: Regen schematics and diff
  run: |
    python scripts/gen_schematics.py --check
    git diff --exit-code pcb/*.kicad_sch
```

The `--check` mode:
1. Regenerates all schematics to a temp dir
2. Runs the oracle on the temp output (connectivity partition check)
3. Diffs against committed schematics
4. Exits non-zero on any mismatch

---

### Phase 4 -- Pipeline Integration & Cleanup

#### [MODIFY] Makefile

```makefile
schematics: netlist
	@echo "Generating schematics from Atopile netlist..."
	python scripts/gen_schematics.py

build: netlist schematics route drc
```

#### [MODIFY] artifacts.yaml

Update the schematics entry from `status: NOT_YET_GENERATED` to a real declaration.

#### [DELETE] Uncommitted hand edits

The dirty working tree has modified `half_bridge.kicad_sch`, `power_input.kicad_sch`, `power_management.kicad_sch`, `sensing.kicad_sch`. These become moot -- `git checkout` them before the first generated commit.

#### [NEW] docs/solutions/tooling-decisions/ update

Record the decision: schematics are now derived output, review lives in `.ato`, synthesized box symbols chosen over harvested for totality.

#### [NEW] scripts/manifest.yaml entry

```yaml
- path: gen_schematics.py
  purpose: "Generate KiCad schematics from atopile netlist (default.net)"
  owner: bennet
  last_run: "2026-07-15"
  category: keep
  disposition: ci-gate
  imports: []
```

---

## Open Questions (Resolved)

| Question | Resolution |
|---|---|
| Power symbols vs. global labels | **Plain labels for everything.** The oracle checks connectivity, not ERC cleanliness. ERC noise from missing power symbols is advisory, not blocking. |
| No-connect markers for single-node nets | **Yes, add no_connect markers** on pins that appear in the components section but are not connected to any multi-node net. Keeps ERC output actionable. |
| `tank` module assignment | **Merge into Half_Bridge.** The tank is the half-bridge load, physically adjacent in the power path. |
| `ct_sense` + `safety` merger | **Merge into Safety_Interlock.** 3 components don't justify their own sheet; functionally part of the safety interlock chain. |
| Branch strategy | **New branch** `feat/gen-schematics` off current branch head. Merge both to main via separate PRs for clean review. |

---

## Verification Plan

### Automated

1. **Generate + oracle**: `python scripts/gen_schematics.py` -- oracle runs automatically. Expected: PASS, all 135 nets, 100 components, partition isomorphic.
2. **kicad-cli parse**: `kicad-cli sch export netlist pcb/temper.kicad_sch -o /tmp/exported.net`. Expected: exit 0.
3. **ERC advisory**: `kicad-cli sch erc pcb/temper.kicad_sch`. Expected: zero `pin_not_connected` / `label_dangling` errors.
4. **Determinism**: `python scripts/gen_schematics.py && git diff --exit-code pcb/*.kicad_sch`. Expected: zero diff.
5. **Change propagation**: Edit `.ato` -> `ato build` -> `gen_schematics.py` -> verify change in exported netlist.

### Manual

- Open generated schematics in KiCad GUI -- verify components appear, labels readable.
- Run `Tools -> Update PCB from Schematic` against a fresh `.kicad_pcb` -- verify 100 footprints.

---

## Estimates

| Phase | Work | Estimate |
|---|---|---|
| P1: Netlist parser + symbol synth | Parse `default.net`, synthesize box symbols, unit tests | ~2h |
| P2: Sheet generator | Grid placement, label emission, hierarchical labels, UUID derivation | ~4h |
| P3: Oracle + CI | Connectivity partition diff, `--check` mode, CI workflow | ~2h |
| P4: Pipeline integration | Makefile, artifacts.yaml, cleanup, docs | ~1h |
| **Total** | | **~9h** |

---

## Scope Boundaries

**In scope:**
- Generator script + oracle + CI gate
- All 6 sub-sheets generated in one shot
- No-connect markers on intentionally-unconnected pins
- Plain net labels only (no power symbols, no drawn wires)

**Deferred:**
- Harvested/"pretty" symbols for manufacturing review (cosmetic pass)
- `ato view` / atopile KiCad plugin integration
- Auto-generating PCB from netlist (`make route` unchanged)

**Outside scope:**
- Fixing bugs in `elec/src/*.ato` itself
- Footprint generation
- PCB layout/routing

---

## Related

- `docs/brainstorms/2026-07-15-generated-kicad-schematics-from-atopile-requirements.md`
- `docs/plans/2026-07-15-001-feat-artifact-identity-provenance-plan.md` (depends on this plan's output)
- `docs/solutions/workflow-issues/resolving-conflicting-sources-safety-critical-schematic-2026-07-14.md`

## Shipped

**Merged in [PR #209](https://github.com/BennetLeff/temper/pull/209) on 2026-07-15.** The `scripts/gen_schematics.py` script now generates all 7 hierarchical KiCad sheets from the atopile netlist. A built-in oracle verifies connectivity partition isomorphism against the source netlist. The CI workflow runs `gen_schematics.py --check` to gate regressions. All 4 phases shipped: symbol synthesizer, sheet assembly, oracle + CI, pipeline integration.
