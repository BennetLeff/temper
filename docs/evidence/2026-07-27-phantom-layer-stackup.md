# Phantom `In3.Cu` / inverted plane-signal stackup: root cause, fix, and measured effect

**Base commit:** `e87e8b90` (branch `docs/methodology-loop-discipline`), asserted via
`scripts/assert-base.sh e87e8b90` at session start (`ASSERT-BASE OK`).
**Fix commit (this task):** `a1fe623e` on `fix/phantom-layer-stackup`
(worktree `.claude/worktrees/agent-a54a62b927b76a2ae`).

**Falsifier, stated up front:** *"The phantom In3.Cu and the excluded outer
layers are a real defect materially limiting routing completion. If fixing
the stackup leaves completion and via count unchanged, then the layer set
was not the binding constraint, and that negative result is the
deliverable."*

**Result: UNVERIFIED at draft time — measurement in progress.** See Part 4.

---

## Part 1 — Reproducing the reported defect (before touching any code)

Verified directly against `pcb/temper.kicad_pcb` at `e87e8b90`, not inferred.

```
$ uv run --no-sync python -c "
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from pathlib import Path
r = parse_kicad_pcb_v6(Path('pcb/temper.kicad_pcb'))
for l in r.stackup.layers:
    print(l.index, l.name, l.layer_type, l.plane_net)
"
0 F.Cu plane PWR_RTN
1 In1.Cu mixed None
2 In2.Cu mixed None
3 In3.Cu mixed None
4 B.Cu plane PWR_RTN
```

Matches the task's reported observation exactly: 5 layers, a fabricated
`In3.Cu`, and both outer layers (F.Cu, B.Cu) typed `plane` instead of
`signal`.

## Part 2 — Root cause (proven, not inferred)

### 2.1 Which branch of `_extract_stackup` executes

`packages/temper-placer/src/temper_placer/io/_parse_board.py` has two
paths: a `setup_stackup.layers`-driven path (used when the `.kicad_pcb`'s
`(setup ...)` block has a `(stackup ...)` sub-block), and a fallback `else`
branch that infers layer count from `ki_board.layers`.

Directly inspected via kiutils:

```
$ uv run --no-sync python -c "
from kiutils.board import Board
b = Board.from_file('pcb/temper.kicad_pcb')
print('setup.stackup:', getattr(b.setup, 'stackup', 'NOATTR'))
"
setup.stackup: None
```

Confirmed: `pcb/temper.kicad_pcb`'s `(setup ...)` block has no `(stackup ...)`
sub-block (matches the task's own grep of the raw file), so the fallback
`else` branch (`_parse_board.py:210-256` pre-fix) executes for this board.

### 2.2 Where the phantom `In3.Cu` comes from

The fallback branch counts copper layers like this (pre-fix):

```python
copper_layers = [ly for ly in ki_board.layers if ".Cu" in getattr(ly, "name", "")]
layer_count = len(copper_layers)
```

Direct inspection of `ki_board.layers`:

```
$ uv run --no-sync python -c "
from kiutils.board import Board
b = Board.from_file('pcb/temper.kicad_pcb')
cu = [ly for ly in b.layers if '.Cu' in getattr(ly,'name','')]
for ly in cu: print(vars(ly))
"
{'ordinal': 0, 'name': 'F.Cu', 'type': 'signal', ...}
{'ordinal': 1, 'name': 'In1.Cu', 'type': 'signal', ...}
{'ordinal': 2, 'name': 'In2.Cu', 'type': 'signal', ...}
{'ordinal': 31, 'name': 'B.Cu', 'type': 'signal', ...}
{'ordinal': 44, 'name': 'Edge.Cuts', 'type': 'user', ...}
```

**`"Edge.Cuts"` matches `".Cu" in name`** — its tail `.Cuts` starts with the
3-character substring `.Cu`. This is a real 4-layer board (`F.Cu`, `In1.Cu`,
`In2.Cu`, `B.Cu`) miscounted as 5, which routes into the `else` branch's
"unusual layer count" fallback (`_parse_board.py:222-224` pre-fix):

```python
else:
    warnings.append(f"Unusual layer count: {layer_count}. Using generic naming.")
    layer_names = ["F.Cu"] + [f"In{i}.Cu" for i in range(1, layer_count - 1)] + ["B.Cu"]
```

For `layer_count=5` this produces exactly `["F.Cu", "In1.Cu", "In2.Cu",
"In3.Cu", "B.Cu"]` — the fabricated `In3.Cu`, confirmed to match the
observed output byte-for-byte.

### 2.3 Where the inverted plane/signal typing comes from

Independently of the count bug, the per-layer type assignment (pre-fix)
was:

```python
for i, name in enumerate(layer_names):
    if name in plane_assignments:
        layer_type = "plane"
        plane_net = plane_assignments[name]
    elif i == 0 or i == layer_count - 1:
        layer_type = "signal"
        plane_net = None
    else:
        layer_type = "mixed"
        plane_net = None
```

`plane_assignments` is built earlier by scanning every zone on the board
and flagging any layer that hosts a zone whose net name contains `"GND"`,
`"VCC"`, `"+"`, or `"PWR"` as substrings:

```python
is_power = ("GND" in zone.netName or "VCC" in zone.netName
            or "+" in zone.netName or "PWR" in zone.netName)
if is_power and ".Cu" in layer:
    plane_assignments[layer] = zone.netName
```

Direct inspection of `pcb/temper.kicad_pcb`'s zones shows **F.Cu and B.Cu
each carry a `PWR_RTN` zone** (among many other per-net zones — `+15V`,
`+15V_LS`, `vcc`, `V_BUS_SENSE`, `ac_l`, `ac_n`, `SW_NODE`, `GATE_HS`,
`GATE_LS`, `PWM_HS`, `PWM_LS`, `DC_BUS_RTN`, ...). `PWR_RTN` matches the
`is_power` substring test (`"PWR" in "PWR_RTN"`), so `plane_assignments =
{"F.Cu": "PWR_RTN", "B.Cu": "PWR_RTN"}`. Since the `name in
plane_assignments` check runs **before** the outer-layer position check,
both outer layers are unconditionally reclassified `"plane"` regardless of
being position 0 / last.

This board pours **per-net copper fill** on its outer layers (creepage and
thermal relief pours for dozens of individual nets — a normal practice for
mains power electronics, confirmed as design intent by
`docs/hardware/POWER_PLANE_DESIGN.md`'s "L1: TOP ... HV copper pours" and
"L4: BOT ... Control signals"). The zone-netname heuristic cannot
distinguish "this whole layer is a single-net plane" from "this layer has
one pour, among many, for a net that happens to have a power-ish name" —
and for this board's design style, the latter is what's actually there.

**Why the corpus test board didn't trip the same symptom**: the corpus
fixture `power_pcb_dataset/corpus/temper/temper.kicad_pcb` has **zero
zones** (`grep -c "(zone" -> 0`), so `plane_assignments` is empty and F.Cu/
B.Cu fall through to the position-based `"signal"` default even under the
pre-fix code — it still had the phantom `In3.Cu` (same count bug), just not
the plane-inversion. This is exactly why `test_astar_3d_production_scale_
spike.py`'s `[corpus]` parametrizations passed while `[production]` failed
at `grids["F.Cu"]` with `KeyError` (`F.Cu` doesn't exist as a routable-layer
grid key once it's typed `"plane"`, and `routing_space.py:85` explicitly
skips any layer whose `layer_type not in ["signal", "mixed"]`).

## Part 3 — What the correct stackup is (step 2 of the task)

**Finding: F.Cu/B.Cu should be signal layers, In1.Cu/In2.Cu should be the
inner GND/PWR reference planes.** This is not a judgment call between two
equally valid options — it is independently confirmed by three sources
that all predate this task and all agree:

1. **`packages/temper-placer/src/temper_placer/core/board.py`** (the
   codebase's own canonical model): `STANDARD_LAYER_ORDER = (F_CU, IN1_CU,
   IN2_CU, B_CU)`, `PLANE_LAYER_INDICES = frozenset({IN1_CU, IN2_CU})`, and
   the `is_plane_layer()`/`is_signal_layer()` helpers built on it. This
   convention is **actively used elsewhere in the router pipeline** —
   not a dead/unused constant:
   - `router_v6/constraints_drc_oracle.py:62`: `INTERNAL_LAYERS =
     frozenset(PLANE_LAYER_INDICES)`
   - `deterministic/stages/via_validation.py:207`: `if is_plane and
     is_plane_layer(layer)`
   - `deterministic/stages/_grid_hv.py`: routable layers computed as
     `STANDARD_LAYER_ORDER` minus `PLANE_LAYER_INDICES`

   `_parse_board.py`'s zone-netname heuristic is a second, independent,
   *ad hoc* reimplementation of the same decision that disagrees with the
   one everything else in the pipeline already trusts.

2. **`docs/hardware/POWER_PLANE_DESIGN.md`** (REQ-ELEC-05, status
   "Implemented"): explicitly specifies "L1: TOP — HV copper pours (DC
   bus, switch node), Power components", "L2: GND — Ground plane (split)",
   "L3: PWR — Power plane (islands)", "L4: BOT — Control signals, digital,
   Gate drive routing". Outer = signal/routing (with power-net copper
   pours as a *secondary* function), inner = dedicated reference planes.

3. **`docs/plans/2026-06-30-001-feat-4-layer-enforcement-plan.md`**
   (status "completed"): "The Temper board is specified as a 4-layer
   design with **inner ground and power planes**."

No document proposes the reverse (outer planes, inner signal); the
`PWR_RTN`-zone-triggered inversion was never a design choice, it is an
artifact of a heuristic that cannot see the difference between "this
layer is entirely one net" and "this layer has 12 different net pours,
one of which is PWR_RTN."

**Not treated as ambiguous.** All three sources agree, so this task
proceeds under: outer layers (F.Cu, B.Cu) = signal, inner layers (In1.Cu,
In2.Cu) = plane, per `core.board.is_signal_layer()`.

## Part 4 — The fix

`packages/temper-placer/src/temper_placer/io/_parse_board.py`
(`_extract_stackup`), commit `a1fe623e`:

1. **Copper-layer counting**: `".Cu" in name` → `name.endswith(".Cu")`
   (both in the `ki_board.layers` count and in the zone-based
   `plane_assignments` loop). Fixes the `Edge.Cuts` miscount; `layer_count`
   for `pcb/temper.kicad_pcb` is now correctly `4`, eliminating the
   `In3.Cu` fabrication path entirely (it's only reached for a genuinely
   unusual count).

2. **Plane/signal precedence for the canonical 4-layer case**: before the
   zone-netname heuristic runs at all, check `core.board.is_signal_layer
   (name)` when `layer_count == 4`. F.Cu/B.Cu are forced `"signal"`
   unconditionally; In1.Cu/In2.Cu fall through to the pre-existing
   zone-based plane detection (unchanged) or default to `"mixed"` if no
   zone is present there yet.

Post-fix, direct re-run of the Part 1 reproduction:

```
0 F.Cu signal None
1 In1.Cu mixed None
2 In2.Cu mixed None
3 B.Cu signal None
layer_count: 4
```

No phantom layer, no inverted planes. (In1.Cu/In2.Cu are `"mixed"` rather
than `"plane"` because this board currently has **zero zones on either
inner layer** — there is no GND/PWR pour poured there yet to detect. This
is a separate, pre-existing gap — inner-layer plane pours were never
implemented, per `docs/plans/2026-07-08-004-feat-4-layer-functional-
stackup-plan.md`'s status: `stale`, "insufficient evidence - needs human
triage" — not something this task's fix scope covers or regresses.)

### Existing unit tests (no regression)

`packages/temper-placer/tests/router_v6/test_stackup_parsing.py`, both
tests, pass unchanged post-fix:

- `test_parse_stackup_from_setup` (2-layer, F.Cu has a GND zone → `plane`):
  layer_count != 4, so the new precedence rule doesn't engage; unaffected.
- `test_parse_stackup_fallback` (4-layer, only In1.Cu has a zone): F.Cu/
  B.Cu have no matching zone in this fixture either way, so old and new
  logic agree. Neither test previously exercised an outer layer *with* a
  matching zone — exactly the gap this fix closes for the real board.

```
$ uv run --no-sync python -m pytest packages/temper-placer/tests/router_v6/test_stackup_parsing.py -q
2 passed in 0.06s
```

## Part 5 — Effect on routing (N>=2 runs, before/after)

<!-- FILLED IN BELOW once measurement runs complete -->

## Part 6 — `test_astar_3d_production_scale_spike.py`

<!-- FILLED IN BELOW -->

## Part 7 — Gate / suite verification

| Check | Result |
|---|---|
| `scripts/assert-base.sh e87e8b90` | OK (session start) |
| `scripts/check_domain_partition.py` | exit 0 |
| `scripts/capacity_budget_gate.py` | exit 0 |
| `scripts/mpn_fabrication_gate.py` | exit 0 |
| `scripts/check_derived_doc_drift.py` | exit 0 |
| `scripts/check_copper_net_consistency.py` | exit 0 |
| `scripts/check_rust_drc_presence.py` | exit 0 |
| `scripts/check_undeclared_imports.py` | exit 0 |
| `scripts/check_stale_extensions.py` | exit 0 |
| `make netlist` | exit 0 (76 assertions) |
| `uv run --no-sync python -m pytest elec/validation -q` | 30 passed |
| Full `router_v6` suite | <!-- FILLED IN BELOW --> |

## UNVERIFIED

<!-- FILLED IN BELOW -->
