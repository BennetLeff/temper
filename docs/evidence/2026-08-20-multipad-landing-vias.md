<!-- provenance: commit=f0ef0e089959b231e4275c7126a765f230d77602 dirty=false
     Branch fix/multi-pad-landing-vias, branched from
     agent/residual-connectivity-diagnosis f0ef0e089 (= origin/main eb5022510
     + the two backbone fixes + that branch's read-only evidence scripts),
     MIN_BARRIER_WIDTH_MM = 12.6 -- the reference configuration every figure
     below is comparable with. Branched there rather than from origin/main so
     the before/after is measured against the exact configuration the
     2026-08-20 residual diagnosis and the 2026-08-19 per-pairing route
     published; f0ef0e089 is a descendant of origin/main and nothing was
     merged.
     pcb/temper.kicad_pcb sha256
     26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b verified
     identical before this task's first command and after its last; never
     opened for writing. Every board below was emitted to a scratch path
     outside the repo.
     Environment: this worktree's OWN .venv (`make venv-isolate` under
     `env -u CONDA_PREFIX`), check_stale_extensions 10/10 fresh, and all 10
     pyo3 modules import-smoke-tested. temper_geometry WAS found unimportable
     mid-session (the exact §7 hazard of the residual diagnosis, triggered by
     switching branches to regenerate the model-E placement) and was rebuilt
     under a private CARGO_TARGET_DIR; every measurement below was taken
     after that rebuild and after both baselines re-reproduced their
     published digests.
     kicad-cli 10.0.5. pcb/temper.kicad_dru regenerated in-process from
     scripts/generate_kicad_dru.py's generate_dru() into each scratch DRC
     directory; pcb/temper.kicad_dru itself was never written.
     Machine: 62 GB RAM, >22 GB free throughout. Another agent's pytest was
     running in a different checkout; no competing route_board.py.
-->
---
title: "Landing vias for intermediate pads: the fix, and the three gates it needs to be safe"
date: 2026-08-20
module: temper-placer
tags: [router, routing, pad-connectivity, vias, drc]
problem_type: routing-completion
status: measured
---

# Every pad, not just the two termini — and why only two of the twenty-three candidate vias may be emitted

## 0. Headline

`_attempt_pad_layer_landing` inspected only `segments[0]` and `segments[-1]`, so
a multi-pad net got a landing via at its two termini and nowhere else. It now
scans every emitted point. **The scan is the easy half.** Three gates decide
what may actually be emitted, and all three were added because measurement —
not reasoning — caught the unconstrained version writing copper that violates.

| | committed placement | model-E placement |
|---|---:|---:|
| pads attached (>=2-pad nets) | 171 -> **172** | 215 -> **216** |
| nets fully pad-connected (all 139) | 60 -> **61** | 82 -> **83** |
| `unconnected_items` (kicad-cli) | 282 -> **281** | 251 -> **250** |
| DRC violations | 603/604 -> **603/604** | 539 -> **539** |
| nets that LOST a pad | **0** | **0** |
| interior landing vias emitted | **1** | **1** |

**This is a +1/+1 fix with zero collateral, not the +12-pad fix the scope
suggested.** The gap between those two numbers is the finding, and §4 is where
it lives.

## 1. The defect, and the scope it actually addresses

Confirmed by re-measurement before any code changed. Both baselines reproduce
their published digests byte-for-byte:

| board | published | **this session** |
|---|---|---|
| model-E placement | `bf9dde9a8d15a2bb…` | **`bf9dde9a8d15a2bb…`** |
| committed placement, routed | `697bad8936b3e16d…` | **`697bad8936b3e16d…`** |
| model-E placement, routed | `af99bd04fa5d873c…` | **`af99bd04fa5d873c…`** |

with `4907/149/152` and `5912/186/124` segments/vias/zones, `282`/`251`
`unconnected_items` and `604`/`539` DRC violations — every published figure.

**Pads unlanded before the fix** (`pad_count - pads_connected`, summed over the
112 nets with >=2 pads):

| | committed | model-E |
|---|---:|---:|
| pads unreached, all >=2-pad nets | **325** | **281** |
| …restricted to nets that emitted copper | **134** | **144** |
| …of those, on the three/four PLANE nets (`gnd`, `+3V3`, `+15V`, `vcc`, `V_BUS_SENSE`) | 133 | 132 |
| **…on ordinary routed nets — this fix's population** | **1** | **12** |

The 12 on model-E are exactly the 12 intermediate pads the residual diagnosis
predicted and measured (`GATE_LS`, `RTD_HW_FAULT`, `V_BUS_SENSE`, `bias`,
`power_in.bypass_relay-coil1`, `refin_n`, `safety.ovp.comp-inp`, `vbias`); the
1 on the committed board is `GATE_LS`. **The addressable population was 12 pads
and 1 pad, not the "every multi-pad net that routes" the brief feared** — most
multi-pad nets that route already land every pad, because the path's layer at
the junction happens to be the pad's own layer and no via is needed at all.

The plane nets' 132/133 are a different mechanism entirely (`_ground_plane.py`
/ `_power_islands.py` drop vias, already measured in `fix/stub-aware-via-drop`)
and this fix does not touch them.

## 2. The fix

`_attempt_pad_layer_landing` now scans every emitted point, not indices 0 and
-1. Three mechanics are load-bearing and each has a regression test:

* **There-and-back, never one-way.** The writer skips a consecutive point pair
  whose layers differ — that pair *is* the via. Inserting the pad-layer point
  alone would delete the copper run from the pad to the next point, breaking
  the route in half to land one pad.
* **The via goes on the pad's CENTRE**, with a sub-tolerance bridge on the
  path's layer when the emitted point is not already exactly there. A Tier-3
  hop terminates on a grid *cell* centre: the first version put `GATE_LS`'s via
  at `(57.0500, 223.0500)` for a pad at `(57.0025, 223.1000)`. That via
  overlaps its pad but is not concentric with it, is not the same node to any
  point-graph connectivity check (`pad_connectivity_audit` buckets at 0.02mm),
  and cannot be deduplicated against a co-located PTH pad by
  `drop_redundant_vias` (same bucket). **`GATE_LS` stayed 2/3.** Landing on the
  pad centre fixed all three at once.
* **First occurrence.** `via_layer_pair_py` derives the pair from the first
  emitted point matching the via and that point's successor. A chained route
  emits the junction pad's coordinate twice; inserting after the second
  occurrence derives the degenerate `(L, L)` pair.

**A blocked interior landing is not a decline.** The terminus decline exists
because a route *ending* on a pad's (x, y) on the wrong layer is copper
claiming to reach a pad it does not reach. A route merely *passing over* an
interior pad makes no such claim, and declining the whole net would discard the
copper that does join the pads it does join. So this pass can only ever add
pads, never remove a net that routes today — which is why the "nets that LOST a
pad" row above is 0 on both placements.

## 3. The three gates, each added because a measurement demanded it

The scan alone emitted **23** candidate vias on model-E. Here is the funnel, and
every step of it was measured on a full route, not reasoned about:

| stage | vias | what it removed |
|---|---:|---|
| raw interior scan | **23** | — |
| **gate 1** — skip pads the route already lands elsewhere | **6** | 17 vias that `drop_redundant_vias` was silently deleting downstream anyway (byte-identical board: `183c7673…` both ways). Correctness of intent, not of output. |
| **gate 2** — via FOOTPRINT free, on EVERY layer | **4** | 2 (`V_BUS_SENSE`, `power_in.bypass_relay-coil1`) |
| **gate 3** — the hole must be drillable | **1** | 3 (`vbias`, `bias`, `RTD_HW_FAULT`) |

### 3a. Gate 2 — a free CELL is a test sized for a trace, not for a via

With only the original single-cell `_layer_free_at`, the pass emitted 6 vias and
kicad-cli attributed **15 violations to 4 of them by name** (matching the via's
own DRC item to the exact recorded landing coordinate, not a radius guess):

```
clearance          9   RTD_HW_FAULT x3, bias x1, vbias x5
drill_out_of_range 3   vbias, bias, RTD_HW_FAULT
hole_to_hole       1   bias
shorting_items     1   V_BUS_SENSE
hole_clearance     1   V_BUS_SENSE
```

Gate 2 tests every grid cell the via's own pad covers (radius
`via_diameter/2 + clearance`), and it tests them on **every copper layer, not
the two the derived pair names**: `via_layer_pair_py` returns `("F.Cu","B.Cu")`
for a landing off an outer layer, and that pair is a THROUGH via — the barrel
pierces the whole stack. The first footprint-aware version checked only the
named pair and let `vbias`/`bias`/`RTD_HW_FAULT` straight through, because the
offending copper was on `In3.Cu`.

It also distrusts a cell that `_unblock_net_pads` CLEARED: those read 0 now, but
a cell inside this net's pad circle can carry a *neighbouring* net's static
copper (`Pad 6 [refin_n] of U8`, 0.635mm from `bias`'s via, is exactly that).
Such a cell counts as free only when it also lies inside one of this net's own
pads.

### 3b. Gate 3 — a via that cannot be drilled is not a landing

Three of the four survivors were `FinePitch` nets, and `FinePitch` specifies
`via_drill_mm = 0.2` — below this board's own 0.3mm minimum hole. kicad-cli:
`Hole size out of range (board setup constraints min hole 0.3000 mm; actual
0.2000 mm)`. **Every** `FinePitch` via on this board has that problem; it is a
pre-existing defect of the netclass table, and the clamp
`fix/via-hole-size-floor` (`9e7f27d2d`) adds at `Via::new` is its board-wide
fix — that branch is not merged here. This pass must not *add* to it to move a
connectivity counter, so a landing whose class drills below the board's own
certified hole is declined. **No threshold was changed, raised, or reasoned
around: the via is simply not emitted.**

Requirement met, and by construction rather than by inspection: every landing
via is sized from the same netclass tables as every other router via, goes
through the same `place_vias` -> `drop_redundant_vias` -> `Via::new` path (so
the 0.254mm annular floor is enforced at construction), and is now additionally
refused if its hole is below the board minimum.

### 3c. What the unconstrained version would have shipped

Recorded because it is the honest counterfactual, and because it is exactly the
"headline" the brief warned about:

| | gates off | **gates on** |
|---|---:|---:|
| pads gained / lost (model-E) | +17 / **-11** | +1 / **0** |
| net pad effect | +6 | **+1** |
| `unconnected_items` | 251 -> 245 | 251 -> **250** |
| DRC violations | 539 -> **591 (+52)** | 539 -> **539 (0)** |
| `clearance` / `shorting_items` / `hole_clearance` / `via_dangling` | +21 / +10 / +8 / +6 | **0 / 0 / 0 / 0** |

The counter-effect the brief predicted **fired, and it was large**: 11 pads on
8 other nets (`+3V3`, `boot`, `hb.gate_hs.driver-p1`,
`power_in.q_relay_drv-g`, `refin_n`, `rtd_pan.r_high_top-inp`,
`safety.thermal.comp-inp`, `safety.uvlo_logic.mon-outa`) were lost to the extra
copper, because a via is stamped as an obstacle on every layer and the router
has no rip-up. **-6 `unconnected_items` bought with +52 DRC violations is not a
fix.** With the gates on, the model-E route is the baseline route plus one via:
`5912` segments (identical), `187` vias (+1), and every DRC category unchanged.

## 4. What this does NOT close, measured

Of the 12 addressable pads on model-E, **1 is landed and 11 are not**:

* **3 declined at gate 3** (`vbias`, `bias`, `RTD_HW_FAULT`) — recoverable the
  moment `fix/via-hole-size-floor` lands, since the drill clamp makes their
  holes legal. **This is the single highest-value follow-up and it is already
  written.**
* **2 declined at gate 2** (`V_BUS_SENSE`, `power_in.bypass_relay-coil1`) —
  the via's own footprint is not clear. `V_BUS_SENSE` was independently
  confirmed dirty (`shorting_items` + `hole_clearance` against
  `rtd_pan.r_low_top-inn` on In3.Cu) when it was emitted, so gate 2 is right
  about at least that one.
* **the rest** (`refin_n` 2/5, `safety.ovp.comp-inp` 2/4) are pads the route
  never passes over at all — no emitted point coincides with them, so there is
  no point at which a via could land. That is a *routing* gap, not a landing
  gap, and it is out of this fix's reach.

Gate 2's own conservatism is honest but coarse, and this is the limitation to
record: the occupancy grid cannot cleanly separate "this net's own pad copper"
from "a neighbour's pad copper that fell inside this net's unblock circle", so
the exemption uses `max(w,h)/2` pad radii and will sometimes trust a cell it
should not, and sometimes refuse one it could take. A real geometric via-drop
validator (the shapely predicate `_ground_plane._find_via_drop_point` already
has) is the correct long-term answer. It was not built here because it is a
larger change than this defect warrants and would need its own measurement.

## 5. Reproduce

```bash
env -u CONDA_PREFIX make venv-isolate
.venv/bin/python scripts/check_stale_extensions.py            # 10/10
# and import-smoke-test all 10 modules -- the freshness gate cannot see a
# module that is fresh but unloadable (residual-diagnosis §7).

# model-E placement: solve on the per-pairing tip, then come back
git checkout --detach origin/agent/per-pairing-placement-route
env -u CONDA_PREFIX make extensions
.venv/bin/python docs/evidence/2026-08-19-per-pairing-route-solve-model-e.py \
    --rows "" --emit /tmp/placement_E.json
.venv/bin/python docs/evidence/2026-08-19-per-pairing-route-apply-placement.py \
    --placement /tmp/placement_E.json --output /tmp/board_E.kicad_pcb
    # -> bf9dde9a8d15a2bb4b0a6126e5ee318fe5e7b34a0e36b5cc1c17e6a620f4bc01
git checkout fix/multi-pad-landing-vias
env -u CONDA_PREFIX make extensions   # then re-verify temper_geometry imports

# route both placements
.venv/bin/python docs/evidence/2026-08-20-multipad-landing-route.py \
    --repo "$PWD" --board-out /tmp/after_c.kicad_pcb --trace-out /tmp/after_c.json
.venv/bin/python docs/evidence/2026-08-20-multipad-landing-route.py \
    --repo "$PWD" --pcb /tmp/board_E.kicad_pcb \
    --board-out /tmp/after_E.kicad_pcb --trace-out /tmp/after_E.json

# pad-level census and net-level before/after diff
.venv/bin/python docs/evidence/2026-08-20-multipad-landing-census.py \
    --repo "$PWD" --board /tmp/after_E.kicad_pcb --trace /tmp/after_E.json
.venv/bin/python docs/evidence/2026-08-20-multipad-landing-diff.py \
    --repo "$PWD" --before <baseline board> --after /tmp/after_E.kicad_pcb

# attribute any DRC delta to the new vias by name
.venv/bin/python docs/evidence/2026-08-20-multipad-landing-attribute-drc.py \
    --repo "$PWD" --before <baseline> --after /tmp/after_E.kicad_pcb \
    --scratch /tmp/attr
```

Routed board digests (sha256):

| board | before | **after** |
|---|---|---|
| committed placement | `697bad8936b3e16ed5168dfe113aead82c2ca93152a345e10df663883c30f370` | **`dfa538f64fdc912bb5157e951692cec450c5c52b55bf6df76cb8e2189caed886`** |
| model-E placement | `af99bd04fa5d873c20e14913f397781a2553f7c8be74f93e9ab39fb5068f5e07` | **`9ba32121752abe1d96f1f3dd02b1405242704eac3d71517c8ca434d1660ab153`** |

Counterfactual (gates off, NOT shipped): model-E `183c767307683e82…`.

## 6. Hard-rule compliance

* `pcb/temper.kicad_pcb` never opened for writing; sha256
  `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b` verified
  before the first command and after the last.
* No clearance, creepage, copper-weight, loop-area, ampacity, annular-ring,
  drill or DRU threshold changed or reasoned around. Gate 3 *reads* the board's
  own declared via drill and declines a via that would fall below it — the
  opposite of relaxing it.
* The two indeterminate pairings (`SELV<->TANK`, `SELV<->SWITCHING`) stay
  fail-closed at 20.0 and 8.0 mm; every model-E verdict here is CONDITIONAL on
  them. `creepage` is 108 before and 108 after on model-E, 106/106 on the
  committed placement — this change generates no creepage finding.
* No check weakened: no test skipped, `xfail`ed, deleted or relaxed; no ratchet
  raised; no allowlist broadened; no `continue-on-error`, `|| true`,
  `# type: ignore` or `# noqa` added. 6 new regression tests added.
* `power_pcb_dataset/drc_ceiling.json` untouched.
* No `_*_py_oracle.py` deleted, consolidated or re-pinned. The Rust A* kernel is
  untouched: this change is entirely at the Python call site, after the search
  returns, exactly as the pinning contract requires.
* `git stash` not used; no pushed history rewritten.
