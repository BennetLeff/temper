---
type: feat
origin: docs/brainstorms/2026-07-08-compound-place-route-loop-requirements.md
contract: docs/brainstorms/2026-07-08-gate-contract.md
status: abandoned
depth: deep
swept: 2026-07-25
swept_basis: "only 0/16 named paths exist"
---
# feat: The Compound Place→Route Loop — All Gates, Unattended Convergence (W5)

## Summary

Turn `PlaceRouteLoop` from a placement-only feedback loop into a **gate-driven
convergence engine**. Introduce the three-state gate contract (`GateResult` /
`GateStatus` / `Violation`) as pure data types, add a `gates: list[Gate]`
registry to the loop, and drive convergence off `all_gates_green(state)` —
which passes only when **every** gate returns `status == CLEAN` (never when a
gate merely returns an empty violation list). Each gate maps its violations to
the **existing** PCL constraint vocabulary (`SeparatedConstraint`,
`KeepoutConstraint`, `AnchoredConstraint`, `LoopAreaConstraint`) through the
existing `_solve_with_delta` path, so no new PCL types are added. The registry
**wraps** the existing `FeedbackClassifier` (it is not replaced): `DrcGate` and
`RoutingGate` compose the classifier's DRC / unrouted-pin / congestion logic;
`PhysicsGate` and `QualityGate` are additive and land after W3/W4.

**Decisive result:** `PlaceRouteLoop.run(all_gates=True)` converges to all-green
on the temper board, unattended, within the existing `MAX_ROUNDS=10` — and
within ≤5 rounds for the near-term `DrcGate + RoutingGate` subset (SC1a).

**Scale:** one new ~200-line data-type module (gate contract), ~250 lines of
concrete gates + a shared `DeltaMapper`, and surgical edits to `loop.py`'s round
structure (stage ordering, `all_gates_green`, UNMEASURED handling). Existing
reused infrastructure: `PlaceRouteLoop._solve_with_delta` (`loop.py:355`),
`PlaceRouteLoop._route_placement` (`loop.py:321`), `FeedbackClassifier.classify`
(`feedback.py:88`), `ConstraintDelta` (`feedback.py:26`), the PCL constraints
(`pcl/constraints.py`), `RoutingResult` (`router_v6/adapter.py:83`),
`CpSatPlacementResult` (`encoder.py:786`), and `run_drc` (`drc_runner.py:162`).

---

## Problem Frame

Today the loop's convergence test is hardwired and boolean-blind. `run()` checks
`completion_rate >= 1.0 and drc_errors == 0` (`loop.py:234`) and then calls
`self.classifier.classify(...)` directly (`loop.py:250`). This has three
structural problems the gate contract exists to fix:

1. **False-zero / two-meanings-of-empty.** `drc_errors == 0` conflates "measured,
   clean" with "couldn't measure." `run_drc` (`drc_runner.py:162`) *raises*
   `DrcRunnerError` when kicad-cli is unavailable or the report is missing — a
   crash today, a silent pass if anyone ever swallows it. This is the
   `run_drc` false-zero bug (see `docs/solutions/best-practices/
   three-silent-failures-measurement-pipeline-2026-07-07.md`) elevated to an
   architectural invariant: a gate that can't measure returns `UNMEASURED`,
   which can never satisfy `all_gates_green`.

2. **Only two signals are consumed.** The loop reads `completion_rate` and
   `drc_errors`; it has no seam for routing ERC (W1), physics (W3 loop
   inductance / thermal / creepage), or quality (W4 octilinear / via count /
   slop). Each of W1–W4 produced a gate and deferred the feedback wiring "to the
   compound loop." This is that wiring.

3. **A central `if/elif` would become a god-function.** Adding each new gate's
   check + delta to `run()` inline would bloat the round loop. The contract's
   answer is a **registry of `Gate` objects**, each pure and testable in
   isolation, with `check()` (measurement) split from `to_delta()` (correction).

A blocking discovery for the plan: **`placer/cp_sat/gate.py` already exists** and
already defines a *different* `GateResult` plus `AcceptanceGate` (the two-tier
audit+DRC acceptance gate, with `inner_passed` / `truth_passed`, covered by
`tests/placer/cp_sat/test_gate.py` and a solution doc). The contract's
three-state `GateResult` **cannot** share that name in that module without
breaking existing code and tests. U1 resolves this by putting the contract types
in a **new sibling module** and leaving `AcceptanceGate` untouched.

---

## Implementation Units

### U1. Gate-contract data types (pure, no loop coupling)

**Goal:** Implement the gate contract's pure data types exactly as specified in
`docs/brainstorms/2026-07-08-gate-contract.md`: `GateStatus`, `GateResult`,
`ViolationType`, `Violation`, `GateStage`, `BoardState`, and the `Gate` base
class. No I/O, no solver, no loop references — this unit is a leaf that
everything else imports.

**Requirements:** R1 (three-state gate result + `Violation` shape + `BoardState`
wrapper); Gate Contract §GateResult/§GateStatus/§GateStage/§Violation/§BoardState.

**Dependencies:** none (pure data).

**Naming-collision resolution (decisive):** `placer/cp_sat/gate.py` is taken by
`AcceptanceGate` + a two-tier `GateResult`. Put the contract types in a **new
module `placer/cp_sat/gates.py`** (plural). Rationale: the two-tier acceptance
gate has its own tests (`test_gate.py`) and a published solution doc
(`two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md`); renaming its
`GateResult` is a wider, riskier blast radius than choosing a fresh module name.
If reviewers prefer honoring the requirement's literal "new `gate.py`," the
fallback is to rename the existing `GateResult` → `AcceptanceResult` (update
`gate.py` + `test_gate.py` + the two-tier solution doc); that is called out as a
tracked alternative, not the default.

**Files:**
- Create: `src/temper_placer/placer/cp_sat/gates.py` — contract data types + `Gate` base.
- Create: `tests/placer/cp_sat/test_gates.py` — data-type invariants.

**Approach:**
```python
class GateStatus(Enum):
    CLEAN = "clean"            # measured, zero violations
    VIOLATIONS = "violations"  # measured, violations found
    UNMEASURED = "unmeasured"  # could not measure — RED, blocks convergence

class GateStage(Enum):
    PLACEMENT = "placement"    # checked after CP-SAT solve, before routing
    ROUTING = "routing"        # checked after routing completes

class ViolationType(Enum):
    CLEARANCE = "clearance"; UNROUTED = "unrouted"
    LOOP_INDUCTANCE = "loop_inductance"; THERMAL = "thermal"
    CREEPAGE = "creepage"; VIA_COUNT = "via_count"; SLOP = "slop"

@dataclass(frozen=True)
class Violation:
    type: ViolationType
    components: tuple[str, ...] = ()
    nets: tuple[str, ...] = ()
    severity: float = 0.0      # violated value (mm, mm², count, ratio)
    threshold: float = 0.0     # limit that was exceeded
    description: str = ""
    context: dict = field(default_factory=dict)   # required_mm, max_area_mm2, location, region

@dataclass(frozen=True)
class GateResult:
    status: GateStatus
    violations: tuple[Violation, ...] = ()
    error_message: str = ""    # only populated when status == UNMEASURED

@dataclass(frozen=True)
class BoardState:
    placement: object          # CpSatPlacementResult
    routing: object | None     # RoutingResult (None before first route)
    netlist: object            # Netlist
    board: object              # Board (zones, stackup)
    design_rules: object | None = None
    routed_pcb_path: Path | None = None

class Gate:
    stage: GateStage
    name: str
    def check(self, state: BoardState) -> GateResult: ...
    def to_delta(self, violation: Violation) -> "ConstraintDelta | None": ...
```

Notes: `GateResult`/`Violation`/`BoardState` are **frozen** — the contract says
all gates receive the same `BoardState` and must not mutate it. `Gate` is a plain
base with two abstract-ish methods (raise `NotImplementedError`); a `Protocol`
is an acceptable alternative but a base class lets `DrcGate`/`RoutingGate` share a
`_classifier` field. Import `ConstraintDelta` under `TYPE_CHECKING` to avoid a
cycle with `feedback.py`.

**Test scenarios:**
- `GateResult(GateStatus.CLEAN)` has empty `violations`, empty `error_message`.
- `GateResult(GateStatus.UNMEASURED, error_message="kicad-cli exit 3")` — status
  is not CLEAN; a helper `is_green(r) == (r.status is CLEAN)` is False.
- A `GateResult` with `VIOLATIONS` but an empty tuple is rejected/asserted-against
  in construction (guard: VIOLATIONS ⇒ at least one violation) — encodes the
  "empty means clean, not couldn't-measure" invariant at the type boundary.
- `Violation` and `BoardState` are hashable/frozen (mutation raises).
- `Gate.check`/`Gate.to_delta` raise `NotImplementedError` on the base.

**Verification:** `test_gates.py` green; `gates.py` imports with zero references
to `loop`, `encoder`, or `router_v6` at module top level (enforce with an import
assertion in the test). No change to `gate.py` / `test_gate.py`.

---

### U2. Gate registry + `all_gates_green`; wrap the FeedbackClassifier

**Goal:** Give `PlaceRouteLoop` a `gates: list[Gate]` registry and an
`all_gates_green(state) -> bool` that returns True iff **every** gate's
`check(state).status == GateStatus.CLEAN`. Implement `DrcGate` (PLACEMENT) and
`RoutingGate` (ROUTING) by **composing** the existing `FeedbackClassifier` —
adapting its `ClassificationResult` into `GateResult` + `Violation` — so the
loop's direct `classify()` call is replaced by gate iteration without deleting
the classifier.

**Requirements:** R1 (registry, `check()`, `all_gates_green` semantics), Gate
Contract §"Integration with PlaceRouteLoop"; the "wraps, not replaces" decision.

**Dependencies:** U1.

**Files:**
- Create: `src/temper_placer/placer/cp_sat/concrete_gates.py` — `DrcGate`,
  `RoutingGate` (composing `FeedbackClassifier`), plus a `classifier→violations`
  adapter.
- Modify: `src/temper_placer/placer/cp_sat/loop.py` — add `gates` attribute,
  `all_gates_green`, and default-registry construction in `__init__`.
- Create: `tests/placer/cp_sat/test_concrete_gates.py`.
- Modify: `tests/placer/cp_sat/test_loop.py` — cover `all_gates_green` truth table.

**Approach:**
- `PlaceRouteLoop.__init__(self, classifier=None, gates=None)`: keep the existing
  `classifier` default (back-compat); when `gates is None`, build the default
  registry `[DrcGate(classifier), RoutingGate(classifier)]`. `PhysicsGate` /
  `QualityGate` are appended by U6 behind the `all_gates`/W3-W4 flag so SC1a runs
  on the DRC+Routing subset alone.
- `DrcGate.check(state)`: run placement-stage DRC. Reuse `AcceptanceGate.truth_gate`
  / `run_drc` on `state.routed_pcb_path` (or a freshly written placement PCB). On
  `run_drc` raising `DrcRunnerError` / nonzero kicad-cli → `GateResult(UNMEASURED,
  error_message=...)`. On errors present → `VIOLATIONS` with one `Violation(type=
  CLEARANCE, components=(...), severity=measured_mm, threshold=required_mm,
  context={"required_mm":...,"location":...})` per DRC error. Zero errors → `CLEAN`.
- `RoutingGate.check(state)`: read `state.routing` (`RoutingResult`). If routing is
  `None` or the router raised upstream → `UNMEASURED`. Else delegate to
  `self._classifier.classify(routing, placement, round_number, previous_unclassified)`
  and adapt: `completion_rate < 1.0` unrouted nets → `Violation(UNROUTED, nets=...)`;
  `drc_violations` → `Violation(CLEARANCE, ...)`. `completion_rate == 1.0` and no
  drc_violations → `CLEAN`. (Note: `RoutingResult` exposes `drc_violations`
  (`adapter.py:97`), while `run()` currently reads `routing.drc_errors` via
  `getattr(..., 0)` — RoutingGate reads the real field, closing that latent gap.)
- `all_gates_green(state)`:
  ```python
  def all_gates_green(self, state) -> bool:
      results = {g.name: g.check(state) for g in self.gates}
      self._last_results = results          # for stage ordering + UNMEASURED (U4/U5)
      return all(r.status is GateStatus.CLEAN for r in results.values())
  ```
  Deltas are **not** injected here (contract's sample inlines them, but we keep
  `check` pure and route injection through U3/U4 so `_solve_with_delta`'s
  backtracking stays the single injection path). `all_gates_green` is a pure
  predicate over cached results.

**Test scenarios:**
- Registry with two CLEAN gates → `all_gates_green` True.
- One gate CLEAN, one UNMEASURED → False (the core invariant: unmeasured ≠ pass).
- One gate CLEAN, one VIOLATIONS → False.
- `DrcGate.check` when `run_drc` raises → `UNMEASURED`, `error_message` carries the
  kicad-cli detail (mock `run_drc` with `side_effect=DrcRunnerError`).
- `RoutingGate.check` with `completion_rate=1.0, drc_violations=[]` → `CLEAN`;
  with unrouted nets → `VIOLATIONS` carrying `UNROUTED` violations that echo the
  classifier's deltas.
- `RoutingGate.check` with `routing=None` → `UNMEASURED`.

**Verification:** `all_gates_green` truth table matches the contract; `DrcGate`/
`RoutingGate` produce violations equivalent to what `FeedbackClassifier` produced
pre-refactor (regression parity against `test_feedback.py` fixtures).

---

### U3. Per-gate delta injection (`to_delta` + shared `DeltaMapper`)

**Goal:** Implement `Gate.to_delta(violation) -> ConstraintDelta | None` for every
gate, mapping each `ViolationType` onto an **existing** PCL constraint through a
single shared `DeltaMapper` (tested once), and inject the resulting deltas via the
loop's existing `_solve_with_delta` backtracking path.

**Requirements:** R2 (delta vocabulary — one mapping per violation type), the
"`check()`/`to_delta()` split + shared `DeltaMapper`" decision, the hard/soft
policy.

**Dependencies:** U1, U2.

**Files:**
- Create: `src/temper_placer/placer/cp_sat/delta_mapper.py` — `DeltaMapper.map(v) -> ConstraintDelta | None`.
- Modify: `src/temper_placer/placer/cp_sat/concrete_gates.py` — each gate's
  `to_delta` delegates to `DeltaMapper`.
- Create: `tests/placer/cp_sat/test_delta_mapper.py`.

**Approach — the vocabulary (all map to existing PCL types; no new PCL):**

| ViolationType | PCL constraint | tier | Notes |
|---|---|---|---|
| `CLEARANCE` | `SeparatedConstraint(a,b, min_distance_mm=severity+δ)` | HARD | existing `feedback.py:243` pattern; δ=0.1mm |
| `UNROUTED` | `AnchoredConstraint(component, region=vicinity_of_pin)` | STRONG | existing `feedback.py:303`; bias comp toward pin |
| `CREEPAGE` | `SeparatedConstraint(net_a,net_b, min_distance_mm=6.0)` | HARD | safety-critical, same as cross-class SEPARATED |
| `THERMAL` | `SeparatedConstraint(hot, sensitive, min_distance_mm=violated_margin+δ)` | HARD | increase hot↔sensitive separation |
| `LOOP_INDUCTANCE` | `LoopAreaConstraint(loop_name, max_area_mm2=measured×0.95)` | SOFT | tightens 5%/round; UNSAT ⇒ surface, not block |
| `VIA_COUNT` | `KeepoutConstraint(zone_name=via_region)` | SOFT | keepout over congested via region → re-route |
| `SLOP` | `KeepoutConstraint(zone_name=slop_region)` | SOFT | region = bbox of offending segments, +2×track_width per side |

- **`KeepoutConstraint` takes a `zone_name`, not a raw bbox** (`constraints.py:474`).
  For the two region-based deltas (`VIA_COUNT`, `SLOP`), `DeltaMapper` synthesizes a
  named keepout zone the way `feedback.py:225` already does (`zone_name=
  f"slop_{hash(bbox)&0xFFFF:04x}"`) and stashes the bbox in the delta so the
  encoder's zone resolution can register it. This is called out as the one place
  where "region" needs a name; U4's `_solve_with_delta` must ensure the synthetic
  zone is passed into `solve_placement(..., zones=...)`.
- **Hard vs soft (R2 + Key Decisions).** Safety-critical (`CREEPAGE`, `THERMAL`,
  `CLEARANCE`) → `ConstraintTier.HARD`; quality (`VIA_COUNT`, `SLOP`,
  `LOOP_INDUCTANCE`) → `SOFT`. The loop's existing backtracking already tries a
  delta and skips on `UnsatError`; hard deltas that go UNSAT surface via the UNSAT
  core (R3), soft deltas are simply skipped.
- **`LOOP_AREA` monotonic tightening.** `max_area_mm2 = measured × 0.95` per round;
  because `_deduplicate_deltas` (`loop.py:479`) keys on `constraint.id`, use a
  stable id `loop_{loop_name}` so each round's tighter value *replaces* the prior —
  giving the 5%/round ratchet for free.
- `to_delta` returns `None` for violations placement can't fix (contract: e.g.
  intra-component clearance) — the loop treats `None` as "no corrective delta,"
  logs, and the gate stays red (blocking) so convergence honestly fails rather than
  silently passing.

**Test scenarios:**
- Each `ViolationType` → expected PCL constraint subclass, tier, and key field
  (`min_distance_mm` / `max_area_mm2` / `zone_name`) with δ applied.
- `LOOP_INDUCTANCE` twice on the same loop → two deltas with the **same id** and
  `max_area_mm2` shrinking by 5% (dedup keeps the tighter one).
- `SLOP` bbox → keepout zone bounds expanded by 2×`track_width` on each side.
- `to_delta(intra_component_clearance)` → `None`.
- Every produced `ConstraintDelta.constraint` is a valid `BaseConstraint` and
  encodes through `_solve_with_delta` without raising (smoke via a real tiny solve).

**Verification:** `test_delta_mapper.py` covers all seven types; the mapper is the
single source of delta construction (grep: gates call `DeltaMapper.map`, never
construct PCL constraints directly).

---

### U4. Stage ordering + BoardState wiring into the round loop

**Goal:** Wire the registry into `run()`'s round structure: build a `BoardState`
each round, run **PLACEMENT-stage** gates right after the CP-SAT solve (before
routing), run **ROUTING-stage** gates after `_route_placement`, and inject the
deltas the fired gates produce through the existing `_solve_with_delta`
backtracking. Replace the hardwired `completion_rate>=1.0 and drc_errors==0`
convergence check with `all_gates_green`.

**Requirements:** R1 (stage separation avoids re-routing on placement-only
violations), R2 (deltas dispatched via existing `_solve_with_delta`), Gate Contract
§GateStage.

**Dependencies:** U2, U3.

**Files:**
- Modify: `src/temper_placer/placer/cp_sat/loop.py` — `run()` round body; add
  `_build_board_state`, `_gates_for_stage`, `_collect_and_inject_deltas`.
- Modify: `tests/placer/cp_sat/test_loop.py` — stage-ordering + injection tests.
- Modify: `tests/integration/test_place_route_loop_temper.py` — end-to-end shape.

**Approach — new round body (preserving existing oscillation/dedup/phase-2):**
1. Solve CP-SAT (`solve_placement`, unchanged, `loop.py:178`). On
   `infeasible/model_invalid` → existing UNSAT return.
2. **PLACEMENT gates:** `state = self._build_board_state(placement, routing=None,
   ...)`; run `[g for g in self.gates if g.stage is PLACEMENT]`. If any is
   `VIOLATIONS`, map each violation through `g.to_delta`, feed the deltas into the
   existing backtracking loop (`_solve_with_delta` → append to `injected_deltas`),
   `continue` to the next round **without routing** (this is the "avoid re-routing
   on placement-only violations" win). If a PLACEMENT gate is `UNMEASURED`, hand to
   U5's handler.
3. Route (`_route_placement`, unchanged). Record the round (`RoundRecord`).
4. **ROUTING gates:** rebuild `state` with the fresh `routing` + `routed_pcb_path`;
   run `[g for g in self.gates if g.stage is ROUTING]`.
5. **Convergence:** `if self.all_gates_green(state):` (which now sees both stages'
   cached results for this round) → apply the existing stability + phase-2 polish
   (`_consecutive_stable_rounds`, `_solve_phase2`) and return SUCCESS. Keep the
   existing `STABILITY_ROUNDS` gate so a one-round fluke doesn't declare victory.
6. Otherwise, collect ROUTING-stage deltas and run them through the same
   backtracking (`_solve_with_delta` with `UnsatError` skip). `None` deltas +
   red gates with no corrective action fall through to the existing "no
   classifiable feedback" / UNSAT-core exits.

- `_build_board_state`: assembles `BoardState(placement, routing, netlist, board,
  design_rules=self._netclass_rules.design_rules if set, routed_pcb_path=...)`.
  For region-based keepout deltas (U3), thread the synthesized zones into the next
  `solve_placement(zones=...)` call by merging them into `self._zones`.
- Keep `FeedbackClassifier` reachable via the gates (U2) — do **not** delete the
  `classify()` call site's supporting machinery (`previous_unclassified`,
  `_extract_unsat_core`); RoutingGate now owns it.

**Test scenarios:**
- PLACEMENT gate fires (DRC clearance) → loop injects a `SeparatedConstraint` and
  re-solves **without** calling `_route_placement` that round (assert route mock
  call-count).
- ROUTING gate fires (unrouted) → `AnchoredConstraint` injected, next round routes.
- Both stages CLEAN across `STABILITY_ROUNDS` rounds → SUCCESS with phase-2 polish
  invoked once (assert `_solve_phase2` called).
- Mixed: placement CLEAN, routing VIOLATIONS → routing delta path taken.
- Oscillation/dedup still fire with gate-produced deltas (regression:
  `_detect_oscillation`, `_deduplicate_deltas` unchanged).

**Verification:** existing `test_loop.py` behaviors still pass (SUCCESS,
backtracking, all-UNSAT, round-limit) with the gate-driven body; new stage-ordering
assertions green; the temper integration test round-trips place→route with the
registry.

---

### U5. UNMEASURED handling + convergence exit reasons

**Goal:** Make the loop honor the three-state discipline end to end: an
`UNMEASURED` gate is logged (with `error_message`), never treated as CLEAN, and
retried next round; if a gate stays `UNMEASURED` for 3+ consecutive rounds, the
loop surfaces it and exits with a dedicated reason. Add the incremental
convergence exit reasons.

**Requirements:** R1 (UNMEASURED blocks convergence), R3 (bounded convergence,
surface blocking constraint), R4 (unattended — escalate, never silently skip);
Gate Contract §GateStatus loop behavior.

**Dependencies:** U2, U4.

**Files:**
- Modify: `src/temper_placer/placer/cp_sat/loop.py` — UNMEASURED bookkeeping, new
  `LoopExitReason` members, `_surface`.
- Modify: `tests/placer/cp_sat/test_loop.py` — UNMEASURED persistence + exit tests.

**Approach:**
- Add `LoopExitReason.GATE_UNMEASURED = "gate_unmeasured"` (and keep the existing
  reasons). Track `self._unmeasured_streak: dict[str, int]` keyed by gate name.
- Per round, after `all_gates_green` caches `self._last_results`:
  - For each gate whose result is `UNMEASURED`: `logger.error("Gate %s UNMEASURED:
    %s", name, result.error_message)`, increment its streak, and **do not** count
    it as green (guaranteed by U2's predicate). Gates that measured this round
    reset their streak to 0.
  - If any gate's streak `>= 3` → return `LoopResult(success=False,
    reason=GATE_UNMEASURED, unsat_core={"gate": name, "error_message": msg,
    "round": round_num}, placement=..., routing=..., rounds=...)`. This is the
    "persistent UNMEASURED → surface and exit" requirement; it is a *measurement/
    tooling* failure surfaced distinctly from constraint UNSAT (`ALL_FEEDBACK_UNSAT`).
  - Streak `< 3` → fall through and continue to the next round (retry) — an
    UNMEASURED gate does not itself produce a delta, but other gates' deltas (and
    a fresh solve) may fix a transient tool/board-load failure.
- `_surface(msg)`: thin logger.error + append to a `self._surfaced: list[str]`
  carried into `LoopResult` for the operator/CLI. Contract's `all_gates_green`
  sample calls `_surface` for UNMEASURED; we centralize it here.
- **Never treat empty-violations-with-UNMEASURED as CLEAN** is already structurally
  guaranteed (U2 predicate over `status`), but add an explicit test to lock it.

**Test scenarios:**
- Gate UNMEASURED once, CLEAN thereafter → loop keeps going, converges (streak
  resets), SUCCESS.
- Gate UNMEASURED for 3 consecutive rounds → exit `GATE_UNMEASURED`, `unsat_core`
  names the gate + `error_message`.
- Gate UNMEASURED but another gate has a workable delta → loop still blocked by the
  unmeasured gate (asserts UNMEASURED ≠ pass even when deltas are available).
- `error_message` from a mocked `run_drc` nonzero exit propagates into the exit's
  `unsat_core`.

**Verification:** three-state discipline is observable at the loop boundary; a
tool crash can never yield SUCCESS; the persistent-UNMEASURED exit is distinct from
constraint UNSAT.

---

### U6. Convergence gate: concrete Physics/Quality gates, `--all-gates` CLI, unattended SC1a/SC1b

**Goal:** Complete the gate suite and the convergence contract. Keep
`MAX_ROUNDS=10`; add the incremental success criteria — **SC1a** (`DrcGate +
RoutingGate` only, ≤5 rounds on temper) as the near-term gate, and **SC1b** (full
suite once W3/W4 land). Implement `PhysicsGate` and `QualityGate`, wire the
`temper optimize --all-gates` flag, and prove unattended convergence + the UNSAT-
core-names-the-blocker path on a broken board.

**Requirements:** R3 (bounded convergence + UNSAT core), R4 (unattended
`--all-gates`, auto-accept hard deltas), Success Criteria SC1a/SC1b/SC3/SC4.

**Dependencies:** U3, U4, U5; PhysicsGate/QualityGate depend on W3/W4 measurement
functions (W3 physics oracle, W4 quality linter).

**Files:**
- Modify: `src/temper_placer/placer/cp_sat/concrete_gates.py` — `PhysicsGate`
  (LOOP_INDUCTANCE / THERMAL / CREEPAGE), `QualityGate` (VIA_COUNT / SLOP,
  octilinear %).
- Modify: `src/temper_placer/placer/cp_sat/loop.py` — `run(..., all_gates=False)`;
  when set, append Physics/Quality to the default registry.
- Modify: `src/temper_placer/cli/__init__.py` — `--all-gates` flag on `optimize`
  (`cli/__init__.py:388` block), pass through to `PlaceRouteLoop.run`; unattended
  = auto-accept hard deltas (no operator prompt), surface UNSAT core on exit.
- Create: `tests/integration/test_all_gates_convergence.py` — SC1a + broken-board
  UNSAT-core test.

**Approach:**
- **PhysicsGate (ROUTING).** Reuse `metrics/physics.py`: `measure_emi`
  (`physics.py:168`, loop areas) for `LOOP_INDUCTANCE`, `measure_thermal`
  (`physics.py:266`, `thermal_margin_c`) for `THERMAL`; creepage from design-rule
  spacing. Wrap each measurement in `try/except` → `UNMEASURED` with the exception
  text (mirrors the contract's `PhysicsGate` example). `LOOP_INDUCTANCE` threshold
  from `pcb_spec.yaml` EMI budget; `THERMAL` from the 150°C shutdown margin already
  encoded in `measure_thermal`.
- **QualityGate (ROUTING).** Consume W4's linter output for `VIA_COUNT` (ceiling),
  `SLOP` (bbox regions), octilinear %. Until W4 lands, ship the gate with a
  measurement shim that returns `UNMEASURED` (honest red) rather than a fake
  `CLEAN` — SC1a never registers it, SC1b does. This keeps the "unmeasured ≠ pass"
  invariant true even for not-yet-wired gates.
- **Convergence gate (R3).** `MAX_ROUNDS=10` unchanged. SC1a asserts the DRC+Routing
  subset converges ≤5 rounds on temper; SC1b (full suite) is verified once W3/W4
  gates measure for real. On `MAX_ROUNDS` exhaustion, return
  `ROUND_LIMIT_EXCEEDED` with `_extract_unsat_core` naming the still-red gate(s).
- **Unattended (R4).** `--all-gates` runs the loop with no prompts; hard deltas are
  auto-accepted (already the loop's behavior — it injects and backtracks without
  asking). On a genuinely over-constrained board (e.g. too small for 6mm creepage),
  the hard `SeparatedConstraint` goes UNSAT, backtracking exhausts, and the loop
  exits with the UNSAT core naming the creepage `SeparatedConstraint` (SC4).
- Result surfacing: extend `LoopResult`/CLI output with per-gate final status so
  "which gate is red" is legible (`temper optimize --all-gates` prints the gate
  table + UNSAT core).

**Test scenarios:**
- **SC1a:** temper board, registry = `[DrcGate, RoutingGate]`, converges all-green
  ≤5 rounds (integration, may mock router to keep it fast/deterministic).
- **SC3:** `temper optimize --all-gates <pcb>` runs to completion unattended,
  produces a routed `.kicad_pcb`, no operator prompt (assert no stdin read).
- **SC4:** intentionally-too-small board → exit with `unsat_core` naming the
  creepage/clearance `SeparatedConstraint` as the blocker.
- PhysicsGate measurement raises → `UNMEASURED` (not a fake CLEAN); loop applies
  U5 persistence handling.
- QualityGate shim (pre-W4) returns `UNMEASURED`; SC1a suite (which excludes it)
  still converges.
- `all_gates=True` registry includes 4 gates; `all_gates=False` includes 2.

**Verification:** SC1a green on temper; `--all-gates` runs unattended end-to-end;
broken-board UNSAT core names the blocking constraint; no gate can pass without
measuring.

---

## Key Technical Decisions

1. **Contract types live in a new `gates.py`, not the existing `gate.py`.** The
   name `GateResult` is already bound to the two-tier `AcceptanceGate`. Reusing
   `gate.py` would break `test_gate.py` and the published two-tier solution doc.
   A new sibling module is the low-blast-radius home for the three-state contract;
   renaming `AcceptanceGate.GateResult → AcceptanceResult` is the tracked fallback
   if reviewers require literal `gate.py`. (Resolves the requirement's "new
   `gate.py`" against on-disk reality.)

2. **`all_gates_green` keys on `status == CLEAN`, never `len(violations) == 0`.**
   This is the whole point of three-state: an `UNMEASURED` gate has zero violations
   *and* zero right to pass. The predicate is a pure `all(r.status is CLEAN ...)`.
   (Gate Contract §GateStatus; requirement R1.)

3. **The registry wraps `FeedbackClassifier`; it does not replace it.** `DrcGate`
   and `RoutingGate` hold a classifier instance and adapt its `ClassificationResult`
   into `Violation`s. The classifier's DRC / unrouted / congestion logic and its
   `previous_unclassified` persistence are preserved verbatim. (Requirement R1
   integration note; "wraps, not replaces.")

4. **`check()` is pure; `to_delta()` + a shared `DeltaMapper` own correction.** The
   contract's inlined "inject inside `all_gates_green`" sample is deliberately
   *not* followed — injection stays in the loop's one backtracking path
   (`_solve_with_delta`) so hard/soft policy, dedup, and UNSAT surfacing keep a
   single home. (Key Decisions: `check`/`to_delta` split.)

5. **No new PCL types — every delta is an existing constraint.** Via/slop →
   `KeepoutConstraint` (with a *synthesized* `zone_name`, since keepout is
   zone-named not bbox-typed), thermal/creepage/clearance → `SeparatedConstraint`,
   unrouted → `AnchoredConstraint`, loop inductance → `LoopAreaConstraint`
   (id-stable so the 5%/round ratchet dedups to the tightest). (Scope Boundaries;
   R2.)

6. **Hard deltas surface, soft deltas skip.** Creepage/thermal/clearance are HARD:
   UNSAT surfaces the core (R3) and, unattended, exits with it (R4). Loop area /
   via / slop are SOFT: tried, skipped on UNSAT. The loop never auto-loosens a
   safety-critical delta. (Key Decisions; R4.)

7. **UNMEASURED is a tooling failure, surfaced distinctly from constraint UNSAT.**
   3+ consecutive UNMEASURED rounds → `LoopExitReason.GATE_UNMEASURED`, separate
   from `ALL_FEEDBACK_UNSAT`. A crashed kicad-cli or oracle can never masquerade as
   convergence. (Requirement R1; ties to the `run_drc` false-zero solution doc.)

---

## Scope Boundaries

### In scope
- Three-state gate contract data types (U1); registry + `all_gates_green` (U2);
  per-gate delta vocabulary over existing PCL (U3); stage ordering + BoardState
  wiring (U4); UNMEASURED discipline (U5); Physics/Quality gates + `--all-gates`
  CLI + SC1a/SC1b (U6).

### Deferred to follow-up / dependent workstreams
- **SC1b full-suite convergence** — verified only after W3 (physics oracle) and W4
  (quality linter) provide real measurements; QualityGate ships as an honest
  `UNMEASURED` shim until then.
- Real-time convergence visualization (loop reports round-by-round via logging).
- Multi-board / parallel-board optimization.
- Schematic-level ERC (detected pre-loop, fail-fast); only routing-induced ERC
  (floating pins) is in the loop, mapped to `AnchoredConstraint`.

### Outside this product's identity
- New PCL constraint types (explicitly forbidden — all deltas reuse existing types).
- router_v6 / CP-SAT encoder replacement — the loop wraps them as-is.

---

## Dependencies / Prerequisites

- **Existing loop machinery (reused, not rebuilt):** `_solve_with_delta`
  (`loop.py:355`), `_route_placement` (`loop.py:321`), `_solve_phase2`,
  `_detect_oscillation`, `_deduplicate_deltas` (`loop.py:479`), `UnsatError`,
  `LoopResult`/`RoundRecord`/`LoopExitReason`.
- **`FeedbackClassifier`** (`feedback.py:88`) and `ConstraintDelta` (`feedback.py:26`)
  — composed by DrcGate/RoutingGate.
- **PCL constraints** (`pcl/constraints.py`) — `SeparatedConstraint`,
  `KeepoutConstraint`, `AnchoredConstraint`, `LoopAreaConstraint`.
- **`RoutingResult`** (`router_v6/adapter.py:83`), **`CpSatPlacementResult`**
  (`encoder.py:786`), **`run_drc`/`DrcResult`** (`drc_runner.py:162`).
- **W1** routing gate (unrouted/DRC/ERC) — RoutingGate consumes it. **W3** physics
  oracle (`metrics/physics.py`) — PhysicsGate consumes it. **W4** quality linter —
  QualityGate consumes it (UNMEASURED shim until ready). W0–W2 stackup/board loading
  as today.

---

## Risks

| Risk | Mitigation |
|------|-----------|
| **`gate.py` name collision** — contract `GateResult` vs existing `AcceptanceGate.GateResult` | U1 uses a new `gates.py`; existing module + tests untouched. Fallback rename is scoped and tracked. |
| **`KeepoutConstraint` is zone-named, not bbox-typed** — via/slop deltas need a region | `DeltaMapper` synthesizes a stable `zone_name` (as `feedback.py:225` already does) and threads the bbox into `solve_placement(zones=...)` via `_build_board_state`. |
| **`run_drc` raises instead of returning a sentinel** | `DrcGate.check` wraps `run_drc` in try/except → `UNMEASURED` with `error_message`; the false-zero can't leak as CLEAN. |
| **`RoutingResult.drc_errors` vs `.drc_violations` mismatch** (loop reads a field that's always 0 via getattr) | RoutingGate reads the real `drc_violations` (`adapter.py:97`), closing the latent gap; note in U2. |
| **PhysicsGate/QualityGate (W3/W4) not yet landed** | Gates ship as honest `UNMEASURED` shims; SC1a runs the DRC+Routing subset; SC1b gated on W3/W4. |
| **Hard-delta UNSAT stalls unattended runs** | Backtracking skips on `UnsatError`; persistent block → UNSAT core exit naming the constraint (R3/R4, SC4). |
| **New deltas re-trigger oscillation/dedup edge cases** | Reuse `_detect_oscillation` + id-stable delta ids (esp. `LoopAreaConstraint`) so the ratchet dedups deterministically; regression tests in U4. |

---

## Test Strategy

- **Unit (pure):** U1 data-type invariants (frozen, VIOLATIONS⇒nonempty,
  UNMEASURED≠CLEAN); U3 `DeltaMapper` covers all seven `ViolationType`s and the δ /
  5%-ratchet / bbox-expansion arithmetic.
- **Unit (gates):** U2 `DrcGate`/`RoutingGate` `check()` with mocked `run_drc` and
  fake `RoutingResult`s — CLEAN / VIOLATIONS / UNMEASURED each; parity against
  `test_feedback.py` fixtures to prove "wraps, not replaces."
- **Loop behavior:** U4 stage ordering (placement gate ⇒ no route that round), U5
  UNMEASURED persistence + `GATE_UNMEASURED` exit, and regression of the existing
  `test_loop.py` exits (SUCCESS/backtracking/all-UNSAT/round-limit).
- **Integration (decisive):** U6 `test_all_gates_convergence.py` — SC1a (≤5 rounds,
  DRC+Routing), SC3 (`--all-gates` unattended, produces routed `.kicad_pcb`, no
  stdin), SC4 (too-small board ⇒ UNSAT core names the blocking `SeparatedConstraint`).
- **Invariant lock:** an explicit test that a gate returning `UNMEASURED` with an
  empty violation tuple never lets `all_gates_green` return True — the architectural
  heart of the contract.
