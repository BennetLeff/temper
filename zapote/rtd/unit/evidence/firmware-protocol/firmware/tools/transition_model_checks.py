#!/usr/bin/env python3
"""Unsafe-state and transition-property checks over the transition model.

Plan: docs/plans/2026-08-02-028-feat-state-machine-model-check-plan.md (U2).

KTD3: each property below is a predicate evaluated over EVERY cell/edge in
the model built by ``transition_model.py`` (U1) -- an exhaustive verdict
with per-cell evidence, not path sampling. The model already contains the
KTD2 wildcard interlock edges, so these checks see the runaway boundary
just like every declared row.

Property set
------------
P1 -- no edge from a faulted state (STATE_FAULT, STATE_RUNAWAY_FAULT) to a
      power-active state (STATE_PREHEAT, STATE_HEATING). This is the
      "power stage disabled while faulted" claim stated as a graph
      property: if it held, no path could re-energize the power stage
      directly out of a fault without first passing through a non-power
      state.

P2 -- every sensor-fault event (the manifest-derived set from
      ``transition_model.derived_sensor_fault_events``) targets a faulted
      state with a non-FAULT_NONE fault code, from every state that
      declares the event.

P3 -- fault-code / fault-target pairing, WITH a documented self-loop
      scoping (see below).

P4 -- no explicit row targets an unknown state or 'TRANSITION_INVALID'.
      (The parser in U1 already refuses to build a model with an unknown
      state/event/fault reference -- P4 re-asserts the invariant over the
      already-built model, as a distinct predicate per KTD3, so a future
      change to the parser that silently swallowed a bad row would still
      be caught here.)

P3 scoping note (deliberate, documented deviation from the plan's literal
wording -- flagged per the task's "implement it and note the disagreement"
instruction)
--------------------------------------------------------------------------
The plan (U2 Approach) states P3 as: "a row targeting a fault state carries
a fault code, and a row carrying a fault code targets a fault state."
Taken completely literally, the first half is violated by two existing,
intentional manifest rows: the FAULT and RUNAWAY_FAULT
EVENT_FAULT_RESET_PERSISTS self-loops
(``(STATE_FAULT, EVENT_FAULT_RESET_PERSISTS) -> STATE_FAULT`` and
``(STATE_RUNAWAY_FAULT, EVENT_FAULT_RESET_PERSISTS) -> STATE_RUNAWAY_FAULT``),
both of which carry no fault code (default FAULT_NONE) because they
persist whatever fault is already latched rather than causing a new one --
the manifest has no field to express "keep the current code." The plan's
own U6 approach text (I-FAULT-EXITS) treats these exact rows as correct,
so this is a plan-wording gap, not a bug to route around by weakening the
check for everyone: this module scopes P3's "row targeting a fault state
carries a fault code" direction to rows that are NOT self-loops
(``from_state != to_state``). Self-loops that stay within the fault domain
don't newly cause a fault, so they're outside the claim. The "row carrying
a fault code targets a fault state" direction is unscoped (checked for
every edge, including self-loops).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Callable, Dict, List

from power_active_mapping import FAULTED_STATES, POWER_ACTIVE_STATES
from transition_model import (
    FAULT_NONE,
    Edge,
    ModelParseError,
    TransitionModel,
    build_model,
    derived_sensor_fault_events,
)


@dataclass
class Violation:
    property: str
    edge: Edge
    message: str

    def to_dict(self) -> dict:
        return {
            "property": self.property,
            "edge": self.edge.describe(),
            "message": self.message,
        }


@dataclass
class CheckResult:
    name: str
    description: str
    passed: bool
    violations: List[Violation] = field(default_factory=list)
    evidence_count: int = 0  # number of cells/edges evaluated

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "passed": self.passed,
            "evidence_count": self.evidence_count,
            "violations": [v.to_dict() for v in self.violations],
        }


def check_p1_no_fault_to_power_active(model: TransitionModel) -> CheckResult:
    """P1: no edge from a faulted state to a power-active state."""
    violations: List[Violation] = []
    evaluated = 0
    for edge in model.edges.values():
        if edge.from_state in FAULTED_STATES:
            evaluated += 1
            if edge.to_state in POWER_ACTIVE_STATES:
                violations.append(Violation(
                    property="P1",
                    edge=edge,
                    message=(
                        f"edge leaves faulted state {edge.from_state} and enters "
                        f"power-active state {edge.to_state} directly"),
                ))
    return CheckResult(
        name="P1",
        description="no edge from a faulted state to a power-active state",
        passed=not violations,
        violations=violations,
        evidence_count=evaluated,
    )


def check_p2_sensor_fault_blocks(model: TransitionModel) -> CheckResult:
    """P2: every sensor-fault event, from every state that declares it,
    targets a faulted state with a non-FAULT_NONE code."""
    sensor_events = derived_sensor_fault_events(model, FAULTED_STATES)
    violations: List[Violation] = []
    evaluated = 0
    for edge in model.explicit_edges():
        if edge.event not in sensor_events:
            continue
        evaluated += 1
        if edge.to_state not in FAULTED_STATES or edge.fault == FAULT_NONE:
            violations.append(Violation(
                property="P2",
                edge=edge,
                message=(
                    f"sensor-fault event {edge.event} from {edge.from_state} "
                    f"targets {edge.to_state} with fault={edge.fault}, "
                    "expected a faulted state with a non-FAULT_NONE code"),
            ))
    return CheckResult(
        name="P2",
        description="every sensor-fault event targets a faulted state with a fault code",
        passed=not violations,
        violations=violations,
        evidence_count=evaluated,
    )


def check_p3_fault_code_discipline(model: TransitionModel) -> CheckResult:
    """P3: fault-code / fault-target pairing (self-loop scoped; see module
    docstring)."""
    violations: List[Violation] = []
    evaluated = 0
    for edge in model.edges.values():
        evaluated += 1
        # Direction 2 (unscoped): a fault code always targets a faulted state.
        if edge.fault != FAULT_NONE and edge.to_state not in FAULTED_STATES:
            violations.append(Violation(
                property="P3",
                edge=edge,
                message=(
                    f"edge carries fault={edge.fault} but targets non-faulted "
                    f"state {edge.to_state}"),
            ))
            continue
        # Direction 1 (scoped: excludes self-loops -- see docstring).
        if edge.to_state in FAULTED_STATES and not edge.is_self_loop:
            if edge.fault == FAULT_NONE:
                violations.append(Violation(
                    property="P3",
                    edge=edge,
                    message=(
                        f"edge enters faulted state {edge.to_state} from "
                        f"{edge.from_state} but carries FAULT_NONE"),
                ))
    return CheckResult(
        name="P3",
        description=(
            "fault code <-> fault-state-target pairing "
            "(self-loops within the fault domain exempted from the "
            "'target implies code' direction; see docstring)"),
        passed=not violations,
        violations=violations,
        evidence_count=evaluated,
    )


def check_p4_no_invalid_targets(model: TransitionModel) -> CheckResult:
    """P4: no explicit row targets an unknown state (defense-in-depth: the
    U1 parser already refuses to build a model with a bad reference)."""
    violations: List[Violation] = []
    evaluated = 0
    state_set = set(model.states)
    for edge in model.explicit_edges():
        evaluated += 1
        if edge.from_state not in state_set or edge.to_state not in state_set:
            violations.append(Violation(
                property="P4",
                edge=edge,
                message=f"edge references a state outside STATE_LIST: {edge}",
            ))
    return CheckResult(
        name="P4",
        description="no row targets an unknown state / TRANSITION_INVALID",
        passed=not violations,
        violations=violations,
        evidence_count=evaluated,
    )


ALL_CHECKS: List[Callable[[TransitionModel], CheckResult]] = [
    check_p1_no_fault_to_power_active,
    check_p2_sensor_fault_blocks,
    check_p3_fault_code_discipline,
    check_p4_no_invalid_targets,
]


def run_all_checks(model: TransitionModel) -> List[CheckResult]:
    return [check(model) for check in ALL_CHECKS]


def main() -> int:
    try:
        model = build_model()
    except ModelParseError as exc:
        print(f"MODEL PARSE ERROR: {exc}", file=sys.stderr)
        return 1

    results = run_all_checks(model)
    ok = True
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"[{status}] {r.name}: {r.description} ({r.evidence_count} cells evaluated)")
        if not r.passed:
            ok = False
            for v in r.violations:
                print(f"    - {v.message}\n      {v.edge.describe()}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
