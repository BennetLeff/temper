---
title: "Placement config's fixed_positions was keyed by bare ref, so any BOM change silently pinned the wrong physical component"
date: "2026-07-17"
category: logic-errors
module: temper_placer
problem_type: logic_error
component: service_object
symptoms:
  - "Adding 5 new components to the design (unrelated to placement) dropped the deterministic placer from 144/144 to 90/149 finite placements under an unchanged production placement config"
  - "No error, no warning -- the config's fixed_positions entries silently resolved to different physical components than the ones their comments describe"
  - "e.g. configs/temper_production_config.yaml's 'C23: [22.0, 83.5] # tank film cap' pinned a gate-driver bypass cap (hb.c_vddb) at a board position chosen for high-voltage tank-capacitor clearance, after a new component was added elsewhere in the design"
root_cause: logic_error
resolution_type: code_fix
severity: critical
tags:
  - temper-placer
  - placement
  - fixed-positions
  - designator-renumbering
  - identity
  - silent-failure
  - config-drift
---

# fixed_positions keyed by bare ref silently misassigns after any BOM change

## Problem

`configs/temper_production_config.yaml`'s `fixed_positions` block (used by
`ComponentAssignmentStage` to pin large/critical components to specific
board coordinates) was keyed by literal KiCad reference designators
(`C23`, `U5`, `R26`, ...). Atopile assigns designators by walking the
component tree in source order and numbering sequentially per prefix —
adding, removing, or reordering *any* component anywhere in the `.ato`
source can shift the numbers assigned to components elsewhere in the
design, even components that were never touched. A config authored
against one BOM snapshot silently pins the *wrong physical component* at
a later snapshot, with no error: the ref still exists, it just now
belongs to a different part.

This was discovered while investigating a placement-count regression
(144/144 → 90/149) after fixing an unrelated bug in `BuckConverter3V3`
(see the related net-count doc) that added 5 new components. Cross-
checking each `fixed_positions` entry's comment (its original design
intent) against what its ref currently resolves to found **8 of 30
entries silently misdirected**:

| Config entry | Comment (intent) | Old ref | Now resolves to | Was meant to be |
|---|---|---|---|---|
| `U3` | IGBT high, near gate driver | U3 | `power_mgmt.buck_3v3.buck` (new buck IC) | `hb.power_loop.q_high` |
| `U4` | IGBT low | U4 | `hb.power_loop.q_high` | `hb.power_loop.q_low` |
| `U5` | UCC21550 gate driver, next to IGBTs | U5 | `hb.power_loop.q_low` (an IGBT) | `hb.gate_hs.driver` |
| `C22` | DC bus HF film cap at the bridge | C22 | `hb.c_vdda` (bootstrap cap) | `hb.c_dc_hf` |
| `C23` | tank film cap | C23 | `hb.c_vddb` (bypass cap) | `tank.c_tank1` |
| `C24` | tank film cap | C24 | `hb.c_dc_hf` (the real HF cap) | `tank.c_tank2` |
| `R26` | litz coil pads (off-board coil) | R26 | `hb.gate_ls.rgs` (gate resistor) | `tank.inductor_conn` |
| `U21` | ESP32-S3, right edge, antenna clearance | U21 | `safety.latch` (logic IC) | `mcu.mcu` |
| `R64` | fan dropper (axial) | R64 | `mcu.r_sda_pullup` | `thermal.r_fan_drop` |

The remaining 12 fixed positions still happened to resolve correctly,
which is exactly what makes this failure mode dangerous: it degrades
*silently and partially*, not loudly and completely. A gate driver and an
IGBT swapping fixed positions, or a critical HF snubber cap landing where
a low-voltage bypass cap was intended, are not cosmetic — they affect
switching-loop parasitic inductance and, in the `C23`/`C24` case, could
have placed a component at a position whose surrounding keep-outs were
sized for a different part's HV clearance requirements.

## What Didn't Work

- Assuming the placement drop was a slot-capacity problem (the initial
  hypothesis, since 5 new components were added). It wasn't: the config's
  slot spacing already had ~6x headroom over the component count.
- The real signal was noticing that `power_mgmt.buck_3v3.l_out-p1`/`p2`
  showed up isolated after the buck-converter fix, tracing that to the
  buck converter itself being a stub (a separate, real bug — see the
  related doc) — and only then, while re-running placement after fixing
  the stub, discovering the *ref identity* had shifted underneath the
  config's fixed positions independently of that fix.

## Solution

Give components a stable identity that survives renumbering, and switch
the config and the consuming code to use it.

**1. Write the identity onto every footprint** (`scripts/gen_pcb_skeleton.py`),
sourced from the atopile netlist's own `sheetpath` (its module-instance
path, e.g. `hb.power_loop.q_high` — this is stable because it's derived
from the `.ato` source's object graph, not from designator-assignment
order):

```python
# Component dataclass gains a sheetpath field, populated from each comp
# node's (sheetpath (names ".../Top::hb.power_loop.q_high") ...) child.
fp.properties = {
    "Reference": comp.ref,
    "Value": comp.value or "?",
    "Footprint": comp.footprint,
    "Sheetpath": comp.sheetpath,  # new
}
```

**2. Read it back** (`packages/temper-placer/src/temper_placer/io/kicad_parser.py`):

```python
comp = Component(
    ref=ref,
    ...
    sheetpath=(fp.properties.get("Sheetpath") if hasattr(fp, "properties") else None) or None,
)
```

**3. Resolve `fixed_positions` keys sheetpath-first, ref-fallback**
(`ComponentAssignmentStage._assign_components_to_slots`):

```python
# Before: comp_by_ref = {c.ref: c for c in netlist.components}
#         for ref, info in self.fixed_placements.items():
#             if ref in comp_by_ref: ...  # placements[ref] = ...

comp_by_ref = {c.ref: c for c in netlist.components}
comp_by_sheetpath = {c.sheetpath: c for c in netlist.components if c.sheetpath}
for key, info in self.fixed_placements.items():
    comp = comp_by_sheetpath.get(key) or comp_by_ref.get(key)
    if comp:
        ...
        placements[comp.ref] = fixed_pos  # resolved ref, not the config key
```

**4. Re-key the YAML** by sheetpath, correcting the 8 wrong entries:

```yaml
# Before:
fixed_positions:
  U3:  [48.0, 16.0]    # IGBT high (HV/Power boundary, near gate driver)
  U5:  [56.0, 22.0]    # UCC21550 gate driver next to IGBTs

# After:
fixed_positions:
  hb.power_loop.q_high: [48.0, 16.0]  # IGBT high (HV/Power boundary, near gate driver)
  hb.gate_hs.driver:    [56.0, 22.0]  # UCC21550 gate driver next to IGBTs
```

Ref-fallback is kept so older fixture-style configs that still use bare
refs (e.g. against boards with no sheetpath data) continue to work
unchanged.

## Why This Works

A KiCad reference designator answers "which Nth part of this type is
this," a number assigned by a global, order-dependent counting pass over
the whole design. It was never meant to be a durable identity — it's
meant to be unique *at one point in time*, for one build. A module-
instance sheetpath answers "which specific place in the circuit is this,"
derived from the object graph the designer actually wrote
(`hb.power_loop.q_high` names *the high-side IGBT of the half-bridge's
power loop*, regardless of what number it happens to get assigned this
build). Keying configuration that must survive across builds by the
former instead of the latter is the root cause; everything else — the
placement regression, the safety-relevant swaps — is downstream of that
one modeling choice.

## Prevention

- **Any config that references a specific component by identity should
  use the most structurally stable handle available, not the most
  convenient one.** Ref is convenient (short, matches the silkscreen) but
  volatile. Sheetpath is verbose but stable. When both exist, prefer
  stable over convenient for anything that needs to survive the BOM
  changing.
- **Cross-check config comments against resolved identity after any BOM
  change**, the way this investigation did manually — or better,
  automate it: a CI check that re-derives each `fixed_positions` entry's
  sheetpath from its position comment (via a simple keyword match, or by
  requiring comments to name the sheetpath directly) and flags drift
  would have caught this before it silently degraded placement quality.
  This is squarely in scope for U7 (CI enforcement) in
  `docs/plans/2026-07-15-001-feat-artifact-identity-provenance-plan.md`
  — the plan already targets "identity drift" as a class of bug to gate
  on; ref-vs-sheetpath drift in placement configs is a specific instance
  of that class.
- **A regression check that only measures component/net *count* won't
  catch identity swaps between same-count runs.** The 144→90 placement
  drop was visible because count changed; if the BOM edit had happened to
  keep the same total count, the 8 misdirected entries would have passed
  every existing check silently, with wrong components at safety-relevant
  positions. A stronger regression check would assert per-sheetpath
  positions match expectations, not just aggregate counts.

## Related Issues

- [`docs/solutions/logic-errors/net-count-metric-definition-mismatch-regression-baseline.md`](net-count-metric-definition-mismatch-regression-baseline.md)
  — the investigation that led here; fixing `BuckConverter3V3`'s stub
  wiring added the 5 components whose designator shifts exposed this bug.
- [`docs/solutions/logic-errors/config-key-whitelisted-but-never-parsed-slot-generation.md`](config-key-whitelisted-but-never-parsed-slot-generation.md)
  — sixth in this arc's silent-config-drop family; this one is arguably
  the most consequential, since it silently misassigns safety/performance-
  critical positions rather than merely using a wrong default value.
- `docs/plans/2026-07-15-001-feat-artifact-identity-provenance-plan.md`,
  units U3 (derived PCB↔netlist identity check) and U7 (CI enforcement)
  — this bug is precisely the failure mode those units exist to close.
  `identity.rs` in `packages/temper-design-bundle` already establishes a
  typed identity foundation; extending fixed-position config validation
  to use it (rather than the ad-hoc sheetpath property added here) is the
  natural next step once U3/U7 land.
