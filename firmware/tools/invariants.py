#!/usr/bin/env python3
"""Declarative invariants module over the U1 model builder.

Plan: docs/plans/2026-08-02-028-feat-state-machine-model-check-plan.md (U5, U6).

KTD5: this module is a CONSUMER of ``transition_model.py`` (U1) -- it loads
the model object U1 already built (states, edges, reachability) and never
re-parses the manifest itself. There is one model and one engine; this
module adds a declarative invariant layer on top of it, not a second one.

KTD7: invariants are declared in ``invariants.yaml`` in a small predicate
format over (state, event, fault, derived flags) -- adding an invariant is
data, not check code. Three invariant "kinds" cover the plan's seed set
(U6) plus the trivial state-induction demonstration in U5's own test
scenarios:

  - ``edge``: a predicate over edges matching an antecedent (an event set,
    optionally restricted to edges whose FROM state is in a derived set)
    that must satisfy a consequent (TO state / fault code constraints).
    This is the shape of I-OVERTEMP-DISABLES and
    I-SENSOR-FAULT-BLOCKS-HEATING, and mirrors U2's P1-P4 property-check
    shape (KTD3) applied to a load-bearing invariant instead of a graph
    hygiene check.

  - ``exit_set``: for a set of named states, the DECLARED (non-implicit --
    see A4) outgoing (event, to_state) pairs must equal an explicitly
    allowed set exactly -- no more, no fewer. This is I-FAULT-EXITS.

  - ``path``: a reachability-based invariant (I-NO-REENTRY), evaluated
    directly against U1's fixed-point closure rather than per-edge
    induction, per KTD5's explicit instruction that path properties use
    the reachability computation.

  - ``state_induction``: the general "base case at STATE_INIT, then
    pre-state satisfies I implies post-state satisfies I for every edge"
    shape KTD5/U5's approach text describes in the abstract. None of the
    four SEED invariants (U6) need this shape -- they are edge/exit-set/path
    predicates, closer to U2's property checks than to single-state
    induction -- but U5's own test scenarios require demonstrating the
    induction engine standalone (a trivial "state is one of the 9 states"
    invariant, verified by base case + per-edge induction with per-edge
    evidence), so it is implemented here and exercised in
    ``test_invariants.py`` rather than left unbuilt.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, FrozenSet, List, Optional, Tuple, Union

import yaml

from power_active_mapping import FAULTED_STATES, POWER_ACTIVE_STATES
from transition_model import (
    INIT_STATE,
    Edge,
    ModelParseError,
    TransitionModel,
    build_model,
    derived_sensor_fault_events,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
INVARIANTS_YAML = Path(__file__).resolve().parent / "invariants.yaml"

_DERIVED_STATE_SETS: Dict[str, Callable[[TransitionModel], FrozenSet[str]]] = {
    "power_active": lambda model: POWER_ACTIVE_STATES,
    "faulted": lambda model: FAULTED_STATES,
    "all_states": lambda model: frozenset(model.states),
}

_DERIVED_EVENT_SETS: Dict[str, Callable[[TransitionModel], FrozenSet[str]]] = {
    "sensor_fault_events": lambda model: derived_sensor_fault_events(model, FAULTED_STATES),
}


def resolve_state_set(model: TransitionModel, spec: Union[str, list, None]) -> Optional[FrozenSet[str]]:
    if spec is None:
        return None
    if isinstance(spec, str):
        if spec not in _DERIVED_STATE_SETS:
            raise ValueError(f"unknown derived state set: {spec!r}")
        return _DERIVED_STATE_SETS[spec](model)
    return frozenset(spec)


def resolve_event_set(model: TransitionModel, spec: Union[str, list, None]) -> Optional[FrozenSet[str]]:
    if spec is None:
        return None
    if isinstance(spec, str):
        if spec.startswith("derived:"):
            name = spec[len("derived:"):]
            if name not in _DERIVED_EVENT_SETS:
                raise ValueError(f"unknown derived event set: {name!r}")
            return _DERIVED_EVENT_SETS[name](model)
        raise ValueError(f"unknown event set spec: {spec!r}")
    return frozenset(spec)


@dataclass
class InvariantViolation:
    invariant_id: str
    detail: str
    edge: Optional[Edge] = None

    def to_dict(self) -> dict:
        d = {"invariant_id": self.invariant_id, "detail": self.detail}
        if self.edge is not None:
            d["edge"] = self.edge.describe()
        return d


@dataclass
class InvariantResult:
    invariant_id: str
    kind: str
    description: str
    passed: bool
    evidence_count: int
    violations: List[InvariantViolation] = field(default_factory=list)
    base_case_holds: Optional[bool] = None  # only meaningful for state_induction

    def to_dict(self) -> dict:
        return {
            "id": self.invariant_id,
            "kind": self.kind,
            "description": self.description,
            "passed": self.passed,
            "evidence_count": self.evidence_count,
            "base_case_holds": self.base_case_holds,
            "violations": [v.to_dict() for v in self.violations],
        }


# ---------------------------------------------------------------------------
# Evaluators, one per invariant "kind"
# ---------------------------------------------------------------------------

def _eval_edge(model: TransitionModel, spec: dict) -> InvariantResult:
    events = resolve_event_set(model, spec.get("events"))
    include_implicit = spec.get("include_implicit", True)
    from_state_in = resolve_state_set(model, spec.get("require_from_state_in"))
    require_to_state = spec.get("require_to_state")
    require_to_in = resolve_state_set(model, spec.get("require_to_state_in"))
    require_to_not_in = resolve_state_set(model, spec.get("require_to_state_not_in"))
    require_fault_not = spec.get("require_fault_not")

    edges = model.edges.values() if include_implicit else model.explicit_edges()

    evaluated = 0
    violations: List[InvariantViolation] = []
    for edge in edges:
        if events is not None and edge.event not in events:
            continue
        if from_state_in is not None and edge.from_state not in from_state_in:
            continue
        evaluated += 1

        reasons = []
        if require_to_state is not None and edge.to_state != require_to_state:
            reasons.append(f"to_state={edge.to_state!r}, expected {require_to_state!r}")
        if require_to_in is not None and edge.to_state not in require_to_in:
            reasons.append(f"to_state={edge.to_state!r} not in {sorted(require_to_in)}")
        if require_to_not_in is not None and edge.to_state in require_to_not_in:
            reasons.append(f"to_state={edge.to_state!r} is in forbidden set {sorted(require_to_not_in)}")
        if require_fault_not is not None and edge.fault == require_fault_not:
            reasons.append(f"fault=={require_fault_not!r}")
        if reasons:
            violations.append(InvariantViolation(
                invariant_id=spec["id"], detail="; ".join(reasons), edge=edge))

    return InvariantResult(
        invariant_id=spec["id"], kind="edge", description=spec.get("description", ""),
        passed=not violations, evidence_count=evaluated, violations=violations,
    )


def _eval_exit_set(model: TransitionModel, spec: dict) -> InvariantResult:
    allowed_exits: Dict[str, list] = spec["allowed_exits"]
    evaluated = 0
    violations: List[InvariantViolation] = []
    for state, allowed_rows in allowed_exits.items():
        allowed_pairs = {(r["event"], r["to"]) for r in allowed_rows}
        actual_edges = [e for e in model.explicit_edges() if e.from_state == state]
        evaluated += len(actual_edges)
        actual_pairs = {(e.event, e.to_state) for e in actual_edges}

        extra = actual_pairs - allowed_pairs
        missing = allowed_pairs - actual_pairs
        for event, to_state in extra:
            edge = model.edges.get((state, event))
            violations.append(InvariantViolation(
                invariant_id=spec["id"],
                detail=f"undeclared exit from {state}: ({event}) -> {to_state} not in allowed set",
                edge=edge,
            ))
        for event, to_state in missing:
            violations.append(InvariantViolation(
                invariant_id=spec["id"],
                detail=f"expected exit from {state} missing: ({event}) -> {to_state}",
            ))
    return InvariantResult(
        invariant_id=spec["id"], kind="exit_set", description=spec.get("description", ""),
        passed=not violations, evidence_count=evaluated, violations=violations,
    )


def reachable_excluding_expansion(model: TransitionModel, start: str, stop_expansion_at: FrozenSet[str]) -> FrozenSet[str]:
    """Fixed-point closure from *start*, EXCEPT states in
    *stop_expansion_at* are added to the reached set but never expanded
    further -- used by I-NO-REENTRY to express "no path ... except through
    STATE_INIT" (reaching STATE_INIT is fine; what STATE_INIT can reach
    afterwards is a fresh self-test cycle, out of scope for this
    invariant)."""
    seen = {start}
    frontier = [start]
    while frontier:
        s = frontier.pop()
        if s in stop_expansion_at:
            continue
        for ev in model.all_cell_events():
            edge = model.edges.get((s, ev))
            if edge is None:
                continue
            if edge.to_state not in seen:
                seen.add(edge.to_state)
                frontier.append(edge.to_state)
    return frozenset(seen)


def _eval_path(model: TransitionModel, spec: dict) -> InvariantResult:
    from_states = resolve_state_set(model, spec["from_state_set"])
    forbidden = resolve_state_set(model, spec["forbidden_target_set"])
    stop_at = frozenset(spec.get("stop_expansion_at", []))

    evaluated = 0
    violations: List[InvariantViolation] = []
    for start in sorted(from_states):
        reached = reachable_excluding_expansion(model, start, stop_at)
        evaluated += len(reached)
        bad = sorted(reached & forbidden)
        if bad:
            violations.append(InvariantViolation(
                invariant_id=spec["id"],
                detail=(f"from {start}, reachable WITHOUT passing through "
                        f"{sorted(stop_at)}: forbidden target(s) {bad} reached"),
            ))
    return InvariantResult(
        invariant_id=spec["id"], kind="path", description=spec.get("description", ""),
        passed=not violations, evidence_count=evaluated, violations=violations,
    )


def _eval_state_induction(model: TransitionModel, spec: dict) -> InvariantResult:
    pred_spec = spec["predicate"]
    allowed = resolve_state_set(model, pred_spec["state_in"])

    def predicate(state: str) -> bool:
        return state in allowed

    base_ok = predicate(INIT_STATE)
    violations: List[InvariantViolation] = []
    if not base_ok:
        violations.append(InvariantViolation(
            invariant_id=spec["id"],
            detail=f"base case failed: predicate false at {INIT_STATE}",
        ))

    evaluated = 0
    for edge in model.edges.values():
        evaluated += 1
        if predicate(edge.from_state) and not predicate(edge.to_state):
            violations.append(InvariantViolation(
                invariant_id=spec["id"],
                detail=(f"inductive step failed: I({edge.from_state}) holds but "
                        f"I({edge.to_state}) does not"),
                edge=edge,
            ))

    return InvariantResult(
        invariant_id=spec["id"], kind="state_induction", description=spec.get("description", ""),
        passed=not violations, evidence_count=evaluated, violations=violations,
        base_case_holds=base_ok,
    )


_EVALUATORS: Dict[str, Callable[[TransitionModel, dict], InvariantResult]] = {
    "edge": _eval_edge,
    "exit_set": _eval_exit_set,
    "path": _eval_path,
    "state_induction": _eval_state_induction,
}


def evaluate_invariant(model: TransitionModel, spec: dict) -> InvariantResult:
    kind = spec.get("kind")
    if kind not in _EVALUATORS:
        raise ValueError(f"invariant {spec.get('id')!r}: unknown kind {kind!r}")
    return _EVALUATORS[kind](model, spec)


def load_invariant_specs(path: Path = INVARIANTS_YAML) -> List[dict]:
    doc = yaml.safe_load(path.read_text())
    specs = doc.get("invariants", [])
    ids = [s["id"] for s in specs]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate invariant id in {path}")
    return specs


def evaluate_all(model: TransitionModel, specs: Optional[List[dict]] = None) -> List[InvariantResult]:
    if specs is None:
        specs = load_invariant_specs()
    return [evaluate_invariant(model, spec) for spec in specs]


def main() -> int:
    try:
        model = build_model()
    except ModelParseError as exc:
        print(f"MODEL PARSE ERROR: {exc}", file=sys.stderr)
        return 1

    results = evaluate_all(model)
    ok = True
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"[{status}] {r.invariant_id} ({r.kind}): {r.evidence_count} pieces of evidence evaluated")
        if not r.passed:
            ok = False
            for v in r.violations:
                print(f"    - {v.detail}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
