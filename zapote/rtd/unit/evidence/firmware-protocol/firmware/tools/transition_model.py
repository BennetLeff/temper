#!/usr/bin/env python3
"""Model builder and reachability core for the firmware state machine.

Plan: docs/plans/2026-08-02-028-feat-state-machine-model-check-plan.md (U1).

KTD1: the manifest (``firmware/transition_table.yaml``) IS the model. This
module parses it into a finite transition graph over the states and events
declared in ``firmware/main/state_machine.h`` and computes reachability from
``STATE_INIT`` by fixed-point closure. Because the graph is finite (9 states
x 23 declared events, plus 2 synthetic wildcard events -- see below), the
closure is exhaustive by construction.

KTD2 -- the runaway interlock as an explicit wildcard edge set
----------------------------------------------------------------
``firmware/main/state_machine.c``'s ``check_runaway_boundary()`` calls
``transition_to(STATE_RUNAWAY_FAULT)`` unconditionally, every tick, from
whatever state the machine is currently in. It is not represented as a row
in ``firmware/transition_table.yaml`` at all -- there is no
``EVENT_RUNAWAY_*`` member in ``EVENT_LIST`` in ``firmware/main/state_machine.h``.
That is the defect this plan exists to close: the highest-severity
protection path in the firmware has zero inbound edges in the declared
transition table and is invisible to any model that only reads the table.

This module makes the interlock a first-class, explicit part of the model:
two synthetic ("implicit") events -- ``EVENT_RUNAWAY_ABSOLUTE_TEMP`` and
``EVENT_RUNAWAY_RISE_RATE`` -- are added as edges from EVERY one of the 9
manifest states to ``STATE_RUNAWAY_FAULT`` with fault code
``FAULT_RUNAWAY_BOUNDARY``. These event names do not exist in the firmware's
``EVENT_LIST`` X-macro; they exist only in this model, standing in for the
two interlock conditions in ``check_runaway_boundary()`` (absolute-temperature
breach and rate-of-rise breach). They are always marked ``implicit=True`` on
the resulting :class:`Edge` so every consumer can tell a modeled interlock
edge from a declared manifest row.

Modeling the interlock from ALL 9 states (not just the 5 "active" states
``firmware/test/gen_transition_table.py`` uses for its own wildcard
expansion) is a deliberate over-approximation: it matches the C-level
"fires from any state, unconditionally, every tick" semantics of
``check_runaway_boundary()``, and adding edges only ever grows the reachable
set -- it cannot hide an unsafe transition that a narrower expansion would
have exposed. See KTD2 in the plan and ``transition_manifest_crosscheck.py``
(U3) for why the test generator's narrower ``ACTIVE_STATES`` expansion is a
documented, non-drift exception rather than something this module mirrors.

Fault-code / self-loop scoping note (P3, transition_model_checks.py)
----------------------------------------------------------------------
Two manifest rows are self-loops that stay within the fault domain:
``(STATE_FAULT, EVENT_FAULT_RESET_PERSISTS) -> STATE_FAULT`` and
``(STATE_RUNAWAY_FAULT, EVENT_FAULT_RESET_PERSISTS) -> STATE_RUNAWAY_FAULT``.
Both carry no fault code in the manifest (the omitted field defaults to
``FAULT_NONE`` per the manifest's own header comment) even though their
target is a fault state -- because they do not newly *cause* a fault, they
persist whatever fault code is already latched. ``transition_model_checks.py``
(U2)'s P3 check is scoped accordingly; see that module's docstring.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Tuple

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIRMWARE_DIR = REPO_ROOT / "firmware"
STATE_MACHINE_H = FIRMWARE_DIR / "main" / "state_machine.h"
TRANSITION_YAML = FIRMWARE_DIR / "transition_table.yaml"

INIT_STATE = "STATE_INIT"
FAULT_NONE = "FAULT_NONE"

# KTD2: the interlock's two conditions, modeled as synthetic events. These
# are NOT members of EVENT_LIST in state_machine.h -- see module docstring.
RUNAWAY_ABS_EVENT = "EVENT_RUNAWAY_ABSOLUTE_TEMP"
RUNAWAY_RATE_EVENT = "EVENT_RUNAWAY_RISE_RATE"
RUNAWAY_WILDCARD_EVENTS: Tuple[str, str] = (RUNAWAY_ABS_EVENT, RUNAWAY_RATE_EVENT)
RUNAWAY_FAULT_STATE = "STATE_RUNAWAY_FAULT"
RUNAWAY_FAULT_CODE = "FAULT_RUNAWAY_BOUNDARY"


class ModelParseError(ValueError):
    """Raised when the manifest references an unknown state/event/fault."""


@dataclass(frozen=True)
class Edge:
    """One (from_state, event) -> to_state transition, with evidence."""

    from_state: str
    event: str
    to_state: str
    fault: str = FAULT_NONE
    implicit: bool = False          # True for KTD2 wildcard interlock edges
    row_index: Optional[int] = None  # manifest row index; None for implicit edges
    notes: Optional[str] = None

    @property
    def is_self_loop(self) -> bool:
        return self.from_state == self.to_state

    def describe(self) -> str:
        origin = "implicit (KTD2 runaway interlock)" if self.implicit else f"manifest row {self.row_index}"
        return f"({self.from_state}, {self.event}) -> {self.to_state} [fault={self.fault}] <{origin}>"


@dataclass
class TransitionModel:
    """The finite transition graph parsed from the manifest."""

    states: Tuple[str, ...]
    manifest_events: Tuple[str, ...]           # events declared in EVENT_LIST
    fault_codes: Tuple[str, ...]
    edges: Dict[Tuple[str, str], Edge] = field(default_factory=dict)

    # -- cell-space helpers ------------------------------------------------

    def all_cell_events(self) -> Tuple[str, ...]:
        """Every event a cell can be enumerated against: declared + wildcard."""
        return tuple(self.manifest_events) + RUNAWAY_WILDCARD_EVENTS

    def outgoing_edges(self, state: str) -> List[Edge]:
        return [e for (s, _ev), e in self.edges.items() if s == state]

    def incoming_edges(self, state: str, *, include_self_loops: bool = True) -> List[Edge]:
        result = [e for e in self.edges.values() if e.to_state == state]
        if not include_self_loops:
            result = [e for e in result if not e.is_self_loop]
        return result

    def explicit_edges(self) -> List[Edge]:
        return [e for e in self.edges.values() if not e.implicit]

    def implicit_edges(self) -> List[Edge]:
        return [e for e in self.edges.values() if e.implicit]

    # -- reachability --------------------------------------------------------

    def reachable_from(self, start: str) -> FrozenSet[str]:
        """Fixed-point closure of states reachable from *start* (exhaustive:
        the graph is finite, so this terminates and covers every path)."""
        if start not in self.states:
            raise ModelParseError(f"reachable_from: unknown start state {start!r}")
        seen = {start}
        frontier = [start]
        while frontier:
            s = frontier.pop()
            for ev in self.all_cell_events():
                edge = self.edges.get((s, ev))
                if edge is None:
                    continue
                if edge.to_state not in seen:
                    seen.add(edge.to_state)
                    frontier.append(edge.to_state)
        return frozenset(seen)

    def interlock_only_states(self) -> Dict[str, List[Edge]]:
        """States whose only non-self-loop incoming edges are implicit (KTD2)
        interlock edges -- i.e. there is no declared manifest row that enters
        the state from elsewhere. Returns {state: [evidence edges]}."""
        result: Dict[str, List[Edge]] = {}
        for state in self.states:
            incoming = self.incoming_edges(state, include_self_loops=False)
            if incoming and all(e.implicit for e in incoming):
                result[state] = incoming
        return result

    def reachability_report(self) -> "ReachabilityReport":
        reachable = self.reachable_from(INIT_STATE)
        unreachable = frozenset(self.states) - reachable
        interlock_only = self.interlock_only_states()
        cells = self.cell_coverage()
        return ReachabilityReport(
            reachable=reachable,
            unreachable=unreachable,
            interlock_only=interlock_only,
            cells=cells,
        )

    def cell_coverage(self) -> Dict[Tuple[str, str], str]:
        """Every (state, event) cell in the full 9x25 space, mapped to
        'declared' (a manifest row backs it), 'implicit' (KTD2 wildcard
        interlock edge), or 'TRANSITION_INVALID' (A3: no row -> invalid by
        construction)."""
        cells: Dict[Tuple[str, str], str] = {}
        for state in self.states:
            for event in self.all_cell_events():
                edge = self.edges.get((state, event))
                if edge is None:
                    cells[(state, event)] = "TRANSITION_INVALID"
                elif edge.implicit:
                    cells[(state, event)] = "implicit"
                else:
                    cells[(state, event)] = "declared"
        return cells


@dataclass
class ReachabilityReport:
    reachable: FrozenSet[str]
    unreachable: FrozenSet[str]
    interlock_only: Dict[str, List[Edge]]
    cells: Dict[Tuple[str, str], str]

    def to_dict(self) -> dict:
        counts = {"declared": 0, "implicit": 0, "TRANSITION_INVALID": 0}
        for v in self.cells.values():
            counts[v] += 1
        return {
            "reachable_states": sorted(self.reachable),
            "unreachable_states": sorted(self.unreachable),
            "interlock_only_states": {
                state: [e.describe() for e in edges]
                for state, edges in sorted(self.interlock_only.items())
            },
            "cell_space_total": len(self.cells),
            "cell_counts": counts,
            "cells": {
                f"{state}|{event}": verdict
                for (state, event), verdict in sorted(self.cells.items())
            },
        }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_state_machine_header(header_path: Path) -> Tuple[Tuple[str, ...], Tuple[str, ...], Tuple[str, ...]]:
    """Extract STATE_*, EVENT_*, and FAULT_* symbol names from state_machine.h
    (and the generated fault list it #includes)."""
    content = header_path.read_text()

    state_names: List[str] = []
    m = re.search(
        r"#define\s+STATE_LIST\(X\)(.*?)(?:#define\s+EXPAND_STATE_ENUM|\Z)",
        content, re.DOTALL)
    if m:
        state_names = [sym for sym, _name in re.findall(r'X\((\w+),\s*"([^"]+)"\)', m.group(1))]

    event_names: List[str] = []
    m = re.search(
        r"#define\s+EVENT_LIST\(X\)(.*?)(?:#define\s+EXPAND_EVENT_ENUM|\Z)",
        content, re.DOTALL)
    if m:
        event_names = [sym for sym, _name in re.findall(r'X\((\w+),\s*"([^"]+)"\)', m.group(1))]

    fault_names: List[str] = []
    fault_list_path = header_path.parent / "fault_list_generated.h"
    if fault_list_path.exists():
        fault_content = fault_list_path.read_text()
        m = re.search(r"#define\s+FAULT_LIST\(X\)(.*?)(?:/\*|\Z)", fault_content, re.DOTALL)
    else:
        m = re.search(
            r"#define\s+FAULT_LIST\(X\)(.*?)(?:#define\s+EXPAND_FAULT_ENUM|\Z)",
            content, re.DOTALL)
    if m:
        fault_names = [sym for sym, _name in re.findall(r'X\((\w+),\s*"([^"]+)"\)', m.group(1))]
    if FAULT_NONE not in fault_names:
        fault_names.append(FAULT_NONE)

    if not state_names:
        raise ModelParseError(f"could not parse STATE_LIST from {header_path}")
    if not event_names:
        raise ModelParseError(f"could not parse EVENT_LIST from {header_path}")
    if not fault_names:
        raise ModelParseError(f"could not parse FAULT_LIST from {header_path} / fault_list_generated.h")

    return tuple(state_names), tuple(event_names), tuple(fault_names)


def parse_manifest_rows(manifest_path: Path) -> List[dict]:
    manifest = yaml.safe_load(manifest_path.read_text())
    return list(manifest.get("transitions", []))


def build_model(
    manifest_path: Path = TRANSITION_YAML,
    header_path: Path = STATE_MACHINE_H,
    *,
    add_wildcard_interlock: bool = True,
) -> TransitionModel:
    """Parse the manifest into a :class:`TransitionModel`.

    Raises :class:`ModelParseError` naming the offending row if a row
    references an unknown state, event, or fault code (test scenario U1-3).
    """
    states, events, faults = parse_state_machine_header(header_path)
    state_set = set(states)
    event_set = set(events)
    fault_set = set(faults)

    rows = parse_manifest_rows(manifest_path)

    edges: Dict[Tuple[str, str], Edge] = {}
    for i, row in enumerate(rows):
        from_s = row.get("from")
        event = row.get("event")
        to_s = row.get("to")
        fault = row.get("fault") or FAULT_NONE
        notes = row.get("notes")

        if from_s not in state_set:
            raise ModelParseError(f"manifest row {i}: 'from' value {from_s!r} not in STATE_LIST")
        if to_s not in state_set:
            raise ModelParseError(f"manifest row {i}: 'to' value {to_s!r} not in STATE_LIST")
        if event not in event_set:
            raise ModelParseError(f"manifest row {i}: 'event' value {event!r} not in EVENT_LIST")
        if fault not in fault_set:
            raise ModelParseError(f"manifest row {i}: 'fault' value {fault!r} not in FAULT_LIST")

        key = (from_s, event)
        if key in edges:
            raise ModelParseError(
                f"manifest row {i}: duplicate (from, event) pair {key} "
                f"(also declared at row {edges[key].row_index})")

        edges[key] = Edge(
            from_state=from_s, event=event, to_state=to_s, fault=fault,
            implicit=False, row_index=i, notes=notes,
        )

    if add_wildcard_interlock:
        for state in states:
            for wildcard_event in RUNAWAY_WILDCARD_EVENTS:
                key = (state, wildcard_event)
                # Wildcard events are synthetic and never appear in the
                # manifest, so no collision with an explicit row is possible
                # by construction -- assert it defensively anyway.
                assert key not in edges, f"unexpected collision on synthetic key {key}"
                edges[key] = Edge(
                    from_state=state, event=wildcard_event, to_state=RUNAWAY_FAULT_STATE,
                    fault=RUNAWAY_FAULT_CODE, implicit=True, row_index=None,
                    notes="KTD2 runaway interlock (check_runaway_boundary, state_machine.c)",
                )

    return TransitionModel(states=states, manifest_events=events, fault_codes=faults, edges=edges)


def derived_sensor_fault_events(model: "TransitionModel", faulted_states: FrozenSet[str]) -> FrozenSet[str]:
    """The "sensor-fault event" set, derived from the manifest rather than
    hardcoded (per U2's P2 approach and shared with U6's
    I-SENSOR-FAULT-BLOCKS-HEATING so the two consumers cannot drift, KTD5).

    An event is in the set iff at least one EXPLICIT (non-implicit) manifest
    row for that event targets a faulted state with a non-FAULT_NONE fault
    code. On the current manifest this yields exactly: EVENT_SELFTEST_FAIL,
    EVENT_PREHEAT_TIMEOUT, EVENT_OVER_TEMP, EVENT_OVER_CURRENT,
    EVENT_FAN_FAILURE, EVENT_PROBE_OPEN, EVENT_PROBE_SHORT,
    EVENT_THERMAL_RUNAWAY, EVENT_COOLDOWN_OVERHEAT -- and excludes
    EVENT_FAULT_RESET_PERSISTS, whose self-loop row carries FAULT_NONE (see
    the module docstring's self-loop scoping note).
    """
    events = set()
    for edge in model.explicit_edges():
        if edge.to_state in faulted_states and edge.fault != FAULT_NONE:
            events.add(edge.event)
    return frozenset(events)


def main() -> int:
    """CLI: build the model and print the reachability report as YAML."""
    try:
        model = build_model()
    except ModelParseError as exc:
        print(f"MODEL PARSE ERROR: {exc}", file=sys.stderr)
        return 1
    report = model.reachability_report()
    print(yaml.safe_dump(report.to_dict(), sort_keys=False, default_flow_style=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
