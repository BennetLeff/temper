<!-- provenance: commit=8e5d74705e98b8f14200cf443c458767d97349d6 dirty=UNKNOWN -->
# Evidence: implementing PhysicsGate sub-check 2 (gate-drive-loop trace geometry)

Status: DONE.

Branching from `fa067a952` per `docs/HANDOFF-2026-08-17.md` and
`docs/evidence/2026-08-17-gate-inductance-and-unwired-kernels.md` (PR #1308,
`fix/gate-inductance-and-unwired-kernels`), which established that
`placer/cp_sat/gates.py::PhysicsGate.check()` sub-check 2 ("Gate-drive
tightness") always reports `UNMEASURED` because its backing module,
`temper_placer.physics.gate_drive`, was never created, and that no other
mechanism in the repo checks gate-drive-loop inductance today.

Board sha256 verified unchanged, start and end:
`9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd`.
`pcb/temper.kicad_pcb` was not modified by this work.

## 1. The intended contract

Found directly in the live call site (`gates.py:907-988`) and corroborated by
the originating design plan (`docs/plans/2026-07-08-005-feat-physics-as-
routing-constraints-plan.md`, requirement R2, and its origin brainstorm
`docs/brainstorms/2026-07-08-physics-as-routing-constraints-requirements.md`):

- `PhysicsGate.check()` imports `gate_drive_loop_area(pcb: Path, gate_net:
  str) -> float | None` and `gate_drive_spacing(pcb: Path, gate_net: str) ->
  float | None` from `temper_placer.physics.gate_drive` — the exact function
  names, signatures, and module path were already fixed by the caller.
- Called once per net in `PhysicsGate._GATE_NETS` (a 2-tuple). `None` for
  both `area` and `spacing` on a given net ⇒ the whole gate returns
  `GateResult(UNMEASURED, ...)` immediately (fail-closed, matching the
  gate's documented "any sub-check that cannot measure ⇒ UNMEASURED"
  contract). A non-`None` value is compared against
  `PhysicsGate._GATE_DRIVE_LOOP_MAX_MM2` (500.0 mm², pre-existing) and
  `_GATE_DRIVE_SPACING_MAX_MM` (2.0 mm, pre-existing) independently — area
  and spacing are two separate measurements, not a single joint one.
- The design plan's R2 describes the *intent*: "measure GATE_H / GATE_L
  routed loop area against its return path" and "edge-to-edge trace-to-return
  spacing." It assumed the loop's nets (device-side net, return net) would
  come from `core/loop_extractor.py::trace_gate_drive_loop`/
  `auto_extract_loops`, with only the geometry computed fresh.

**This last assumption does not hold on the real board — confirmed by direct
inspection, not assumed:**

1. `classify_component` (`loop_extractor.py:83`) only classifies a
   component as `power_switch` when its reference starts with `"Q"`
   (`ref.startswith("Q")` gate). On the real board the half-bridge switches
   are **`U4`** (high side) and **`U5`** (low side) — both
   `Package_TO_SOT_THT:TO-247-3_Vertical` — confirmed by reading their pad
   nets directly (`U4`: gate → `hb.power_loop.q_high-g`, drain →
   `+170V_BUS`, source → `SW_NODE`; `U5`: gate → `GATE_LS`, drain →
   `SW_NODE`, source → `hb-gnd`). `Q1`/`Q2` are `Package_TO_SOT_SMD:SOT-23`
   parts wired to `power_in.bypass_relay-coil2`/`power_in.q_relay_drv-g` and
   `discharge.k_dis1-coil2`/`discharge.q_dis_drv-g` respectively — a relay
   driver and a discharge-circuit driver, **not** the half-bridge switches.
   `find_power_switches`/`detect_half_bridge_topology` therefore find
   nothing useful on this board.
2. Independently of (1): `trace_gate_drive_loop` calls `get_pin_net(switch,
   ["GATE", "G"])`, which keys off a functional pin *name*. A `Netlist`
   built by `io.kicad_parser.parse_kicad_pcb` — the only netlist available
   for a routed board — populates `Pin.name` from the pad **number**
   (confirmed by reading `fixtures/synthetic.py`'s and
   `profiling/validation/invariants.py`'s own `Pin("1", "1", ...)`
   construction pattern, and by `netlist.py`'s field-install; a `.kicad_pcb`
   layout file carries no schematic pin-function data at all). There is no
   pin literally named `"GATE"` to find. This is the identical root cause
   `docs/evidence/2026-08-11-loop-area-cycle-basis-order-spike.md` already
   documented for sub-check 1: `auto_extract_loops` finds **zero** loops of
   any type on `pcb/temper.kicad_pcb`.

So the plan's literal "topology from loop_extractor, geometry from the
route" design is unreachable here. **Interpretation adopted** (stated per
the task's own instruction to flag ambiguity): re-derive just enough
topology directly from the parsed board's pad-to-net connectivity —
generically, with no hardcoded reference designators — rather than using
`loop_extractor`. Full rationale and algorithm are in the module docstring
of `physics/gate_drive.py`; summary in §2 below.

## 2. What was implemented, and where

**`packages/temper-placer/src/temper_placer/physics/gate_drive.py`** (new,
321 lines). Public entry points match the fixed contract exactly:
`gate_drive_loop_area(routed_pcb_path, gate_net)` /
`gate_drive_spacing(routed_pcb_path, gate_net)`, both `float | None`,
fail-closed (`None`) on any measurement failure — never a false `0.0`.

Internally:

1. **Forward walk** (`_walk_forward`): starting at `gate_net` (the
   driver-output net, e.g. `"GATE_HS"`), extend through any 2-pad,
   `R`/`L`-prefixed passive whose other pad lands on a net not yet seen —
   generically bridging a series gate resistor's driver-side net to its
   device-side net (handles the real board's high-side loop, where `R18`
   splits `GATE_HS` from `hb.power_loop.q_high-g`). Each hop is evaluated
   against a snapshot of the net set taken **before** that iteration's
   extensions (a real bug caught by the test suite, see §5) so the switch
   check re-runs between every single hop rather than chaining two passives
   in one pass.
2. **Switch detection** (`_find_switch`): stop the walk the moment a net in
   the forward set is touched by a component whose footprint name contains
   `TO-247`/`TO-220`/`TO-263` — the same package signal
   `classify_component` already uses for power-switch detection, generalized
   by dropping its incorrect `ref.startswith("Q")` prerequisite (§1.1). More
   than one candidate ⇒ ambiguous ⇒ `None` (fail closed, never guess).
3. **Return-net selection** (`_pick_return_net`): from the switch's
   remaining pads, prefer a net whose name contains
   `gnd`/`rtn`/`ground`/`return` (case-insensitive — the standard EE
   return-net naming convention); else the unique remaining net not
   starting with `"+"` (excludes fixed-supply-rail names); else ambiguous ⇒
   `None`.
4. **Geometry**: convex-hull area over the combined go+return trace
   endpoints (`temper_geometry.convex_hull_area_py`, the identical Rust
   kernel `physics/loop_area.py`'s sub-check 1 uses) and minimum
   endpoint-pair spacing between the go and return trace arms
   (`temper_drc_rs.min_hv_lv_trace_clearance`, the identical kernel and the
   identical endpoint-pair approximation already used in production by
   `validation/trace_analyzer.py`'s HV/LV clearance metric — not a true
   segment-to-segment distance; that approximation is pre-existing
   production precedent, not introduced here).

**`placer/cp_sat/gates.py`**: corrected `PhysicsGate._GATE_NETS` from the
stale `("GATE_H", "GATE_L")` to the real board's `("GATE_HS", "GATE_LS")`.
`configs/gate_driver_constraints.yaml` already documents this rename in its
own comment ("`GATE_HS` # was `\"GATE_H\"` -- real board net"). Without this
correction, `gate_drive.py`'s functions would never find a routed trace on
either net regardless of how correct the measurement logic was — sub-check 2
would stay `UNMEASURED` for a different reason than before, which would not
satisfy "wire it in so the sub-check actually runs." `_IGBT_REFS = ("Q1",
"Q2")` is a **separate, pre-existing** staleness belonging to sub-check 3
(thermal via count) — flagged in a code comment for the owner, not touched;
`physics.gate_drive` does not use `_IGBT_REFS`.

**`packages/temper-placer/tests/physics/test_gate_drive.py`** (new, 249
lines, 19 tests): synthetic `Netlist`/`Component`/`Pin` fixtures shaped
exactly like the two real gate-drive loops (direct switch-on-net for
`GATE_LS`/`U5`; one series-resistor hop for `GATE_HS`/`R18`/`U4`), plus
ambiguous-switch, ambiguous-return-net, walk-exhausted, and
non-R/L-component fail-closed cases, plus the area/spacing geometry helpers.

## 3. Proof it is live

- **Import succeeds.** `PhysicsGate.check()`'s sub-check 2 previously always
  raised `ImportError` (module didn't exist) and returned `UNMEASURED`
  before ever calling anything. It now imports and runs real logic.
- **19/19 new unit tests pass**, including a real bug the tests caught and a
  fix required to pass (§5).
- **Full regression check**: `pytest packages/temper-placer/tests/physics/`
  — 1052/1052 pass (0 regressions from the new module or the `_GATE_NETS`
  edit). `pytest tests/placer/cp_sat/test_physics_gate.py -k "not
  creepage"` — 9/9 pass. The 6 `IECCreepageGate`-specific tests in that same
  file fail in this freshly-built isolated venv with `"No resolvable
  kicad_pro ... call copy_kicad_project_sidecar"` — a pre-existing sidecar
  project-file fixture issue in `IECCreepageGate` (an unrelated class;
  confirmed by inspecting the diff, which touches nothing in
  `IECCreepageGate`), not caused by this change.
- `scripts/check_physics_provenance.py` — passes (0 undocumented module-
  level float constants added; `gate_drive.py` has none).
- `ruff check` — clean on all 3 changed/added files. `mypy` — the new
  module produces zero errors of its own (the one error surfaced while
  type-checking it is in a pre-existing, unrelated stub,
  `stubs/temper_design_bundle_python/__init__.pyi:913`, not touched by this
  change).
- **Direct invocation against the real board** (`.venv` built in this
  worktree via `make venv-isolate`, isolated from the shared repo `.venv`
  per the hard rule): `gate_drive_loop_area`/`gate_drive_spacing` execute
  end to end, the forward walk correctly finds `U4`/`U5` (not `Q1`/`Q2`)
  and correctly resolves `SW_NODE`/`hb-gnd` as the return nets — exactly
  matching the by-hand topology trace in §1. See §4 for the measured
  result.
- **Where `PhysicsGate` is registered**: constructed in
  `placer/cp_sat/_loop_core.py:190`, gated behind an `all_gates=True` flag
  to the W5 place-route loop (`cpsat_run_gated_loop`). Grepping the
  production tree, **no non-test caller currently passes `all_gates=True`**
  — this flag is only exercised from tests today. That is a separate,
  pre-existing gap in how the whole `PhysicsGate` (not just sub-check 2) is
  wired into the default routing loop, out of this task's scope (the task
  was the sub-check's own `UNMEASURED`-by-`ImportError` bug, which is now
  fixed) — flagged here for the owner rather than silently left implicit.
- **Sub-check 1 still blocks the aggregate `PhysicsGate.check()` on the real
  board.** `commutation_loop_area` (sub-check 1) was already confirmed
  unreachable on this board by
  `docs/evidence/2026-08-11-loop-area-cycle-basis-order-spike.md` (same
  root cause as §1.2: `auto_extract_loops` finds zero loops), and PR #1308
  explicitly flagged this as "a separate, larger, pre-existing gap...
  flagged for the owner, not attempted here." Calling
  `PhysicsGate().check(BoardState(routed_pcb_path=<real board>))`
  end-to-end therefore still returns `UNMEASURED` with
  `error_message="commutation-loop area: trace extraction failed"` —
  sub-check 1's failure, not sub-check 2's, and it fires first. To prove
  sub-check 2 itself is fixed and live, it was also exercised in isolation
  (replicating `gates.py`'s exact sub-check-2 loop against the real board
  directly, bypassing sub-check 1) — see §4.

## 4. The value it computes on the real board

Both `gate_drive_loop_area` and `gate_drive_spacing` return `None` for
**both** `GATE_HS` and `GATE_LS` on the committed board — i.e. sub-check 2,
run in isolation, reports **`UNMEASURED`** for each loop, for two different
and individually verified reasons:

| Loop | Forward walk | Switch found | Return net resolved | Why it's `UNMEASURED` |
|---|---|---|---|---|
| `GATE_HS` | `{GATE_HS, hb.power_loop.q_high-g}` (1 resistor hop through `R18`) | `U4` (`TO-247`) | `SW_NODE` | `SW_NODE` has **0 discrete routed-trace segments** in `parse_kicad_pcb`'s output. It does carry copper physically — the board has **2 zone (copper-pour) entries** on `SW_NODE` — but zone-fill geometry is not exposed by `ParseResult`/`result.traces` at all (confirmed: `ParseResult` has no `zones` attribute). This is a structural limitation shared with sub-check 1's own `commutation_loop_area`, which is trace-only by the same precedent, not something introduced by this module. `GATE_HS` itself (the driver-side net) also has 0 discrete traces but 2 zone entries — the driver→resistor hop may likewise be zone-implemented rather than traced. |
| `GATE_LS` | `{GATE_LS}` (direct — `U5`'s gate pin sits on `GATE_LS` itself, no resistor split) | `U5` (`TO-247`) | `hb-gnd` | `hb-gnd` has **zero copper of any kind** — 0 discrete trace segments **and** 0 zone entries (confirmed by grepping every `(zone ...)` block's `net_name` in `pcb/temper.kicad_pcb`: `hb-gnd` never appears). This is not a measurement-methodology gap; the low-side gate-drive loop's return-reference net appears to be **genuinely unrouted** on the committed board. |

For context, `GATE_LS` itself *is* well-routed (39 discrete trace segments
plus 4 zone entries) and the topology walk correctly finds it directly on
`U5`'s own gate pin with zero ambiguity — the measurement chain works
correctly up to the point where it needs return-path copper that does not
exist (in the trace sense) on this board today.

**This is a real, non-trivial finding, not a null result.** It says: even
with the missing-module bug and the stale-net-name bug both fixed, this
specific check cannot certify the gate-drive loops on the currently
committed board as either safe or unsafe, because:

- the high-side loop's return path is likely present as copper (zone-filled)
  but invisible to this (and sub-check 1's) trace-only measurement
  methodology — a "verification blind spot" in the same family the handoff
  documents for `--refill-zones`-blind DRC measurements (mechanism 4); and
- the low-side loop's return path is not present as copper at all.

**Not attempted, and explicitly flagged rather than silently left out**:
teaching `physics/gate_drive.py` (or `parse_kicad_pcb`/`ParseResult`) to see
zone-fill copper. `ParseResult` does not expose zone geometry to any Python
caller today, so this would be a new capability spanning the Rust parse
engine, not a fix scoped to one sub-check — the same category of effort the
project already treats as a dedicated, separate piece of work (see
`--refill-zones`, PR #1298). Extending it here would be exactly the kind of
overreach the task instructions warn against ("implement what was
designed, not what you would design").

## 5. A real bug the new tests caught

`_walk_forward`'s first draft mutated `forward_nets` in place while
iterating `netlist.components` in a single pass. On a synthetic netlist
shaped like the real high-side loop plus its return-path pulldown resistor
(`R18`: `GATE_HS`→`hb.power_loop.q_high-g`; `R19`:
`hb.power_loop.q_high-g`→`SW_NODE`; `U4` on `hb.power_loop.q_high-g`), both
`R18` and `R19` were treated as forward hops within the *same* iteration
(because `R19`'s net was already present in the just-mutated `forward_nets`
by the time the loop reached it), which would have silently pulled the
return-path net (`SW_NODE`) into the "go" side of the loop before the
switch check ever ran again — corrupting the measurement rather than
failing closed. Fixed by evaluating every hop against a snapshot of the net
set taken before that iteration's extensions, so the switch-detection check
re-runs between every single hop (`gate_drive.py::_walk_forward`,
"Extend by exactly one hop per outer iteration" comment). Caught by
`test_walk_forward_does_not_cross_a_second_series_resistor_once_switch_found`.

## 6. The threshold situation

`PhysicsGate._GATE_DRIVE_LOOP_MAX_MM2 = 500.0` and
`_GATE_DRIVE_SPACING_MAX_MM = 2.0` **already existed** in `gates.py` before
this task (marked "Thresholds (SSOT — do not duplicate)"), and this task did
not add, change, or re-derive them — only the measurement functions that
feed them were implemented. Per the hard rule against inventing thresholds,
their provenance was checked rather than assumed:

- The design plan (`docs/plans/2026-07-08-005-...`) cites external sources
  for three of its four sub-checks: R1 (commutation loop, 2000 mm²) cites
  "Infineon AN half-bridge IGBT design guide — commutation-loop area
  rule-of-thumb"; R3 (thermal vias) cites IPC-2152; R4 (creepage, 6 mm)
  cites IEC 60335-1 Table 16 (recovered verbatim, may be relied on per the
  task's own instructions).
- **R2 (gate-drive, 500 mm² / 2 mm) carries no citation anywhere** — not in
  the plan's "External References," not in its originating brainstorm
  (`docs/brainstorms/2026-07-08-physics-as-routing-constraints-requirements.md`),
  not in the gate contract doc. The brainstorm states the numbers directly
  ("loop area ≤ 500 mm² for EACH of GATE_H and GATE_L loops... Trace-to-
  return spacing... ≤ 2mm") with no datasheet or standard behind them.

**Conclusion**: the 500 mm²/2 mm thresholds appear to be uncited engineering
judgment, not a sourced datasheet or standards value — unlike their three
siblings in the same plan. This task did not fabricate them (they predate
it and are out of its scope to change — "never invent... a threshold"
cuts against introducing a new one, and there already was one before this
work started), but their lack of traceable sourcing is flagged here
honestly for the record, per the task's instruction to report the
threshold situation precisely. It is presently moot for the real board's
result: sub-check 2 reports `UNMEASURED` for both loops (§4), so no
comparison against either threshold ever executes. It would matter the
moment either return path gets a measurable trace (e.g. if `hb-gnd` is
routed, or if zone-copper visibility is added per §4's flagged follow-up):
whatever number results would be compared against an uncited 500 mm²/2 mm,
which is worth an owner decision (source them properly, or mark them
explicitly as design judgment rather than "SSOT").

## 7. Summary

| Item | Status |
|---|---|
| Intended contract | Recovered from the live call site + design plan; documented in §1 |
| `physics/gate_drive.py` | Implemented (321 lines), matches the fixed contract exactly |
| Wired in | Import succeeds; `_GATE_NETS` corrected to match real board net names |
| Proof of liveness | 19/19 new unit tests, 1052/1052 existing physics tests unaffected, direct real-board invocation traced end to end |
| Value on the real board | `UNMEASURED` for both `GATE_HS` and `GATE_LS` — for two distinct, individually-diagnosed reasons (zone-only copper invisible to trace-based measurement; genuinely unrouted return net) |
| Threshold | Pre-existing, not touched; flagged as uncited engineering judgment (unlike its three sibling sub-checks' thresholds) |
| `pcb/temper.kicad_pcb` | Unmodified — sha256 verified unchanged before and after |
