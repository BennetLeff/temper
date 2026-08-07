#!/usr/bin/env python3
"""Cross-check the two independently-maintained transition manifests.

Plan: docs/plans/2026-08-02-028-feat-state-machine-model-check-plan.md (U3).

This is the fix for the root defect the plan exists to close: the
production manifest (``firmware/transition_table.yaml``, parsed by
``transition_model.py``/U1) and the test generator's hardcoded transition
list (``firmware/test/gen_transition_table.py``'s ``TRANSITIONS``) were two
independently maintained sources of truth with nothing reconciling them.
Only the test-side list encoded the runaway wildcard rows at all -- this
module is what makes that fact machine-checked instead of merely observed.

Per KTD4, the two manifests "must agree" -- compared row-for-row on
``(from, event, to, fault)`` -- MODULO the interlock wildcard rows, whose
STATE-SET divergence is a documented, deliberate KTD2 exception (the model
fires the interlock from all 9 manifest states; the test generator only
expands its wildcard rows over its narrower ``ACTIVE_STATES`` list, for
test-mechanics reasons unrelated to the interlock's real semantics). That
exception covers ONLY the state-set breadth of the wildcard expansion --
this module still cross-checks that the wildcard rows' (to, fault) VALUES
agree between the two manifests wherever both declare them, because a
values-level divergence there (e.g. one manifest routing the interlock to
a different state) would be real drift, not a documented exception.

Three checks, in order
-----------------------
1. ``crosscheck_explicit_rows`` -- every non-wildcard row, row-for-row on
   (from, event, to, fault), in both directions (missing-from-test,
   missing-from-production, value mismatch).
2. ``crosscheck_wildcard_rows`` -- the interlock wildcard rows: values must
   agree on the state-set overlap (the test generator's ACTIVE_STATES);
   the state-set difference (production's other 4 states) is recorded as a
   documented KTD2 exception, not an error.
3. ``crosscheck_codegen_drift`` -- regenerates ``firmware/main/transition_table.h``
   in memory from the production manifest (reusing
   ``firmware/tools/gen_transition_table.py``'s own render pipeline) and
   diffs it against the committed file, catching codegen drift as part of
   the same gate.

Everything here is read-only: it never writes ``firmware/transition_table.yaml``,
``firmware/test/gen_transition_table.py``, or ``firmware/main/transition_table.h``.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Dict, List, Tuple

from transition_model import (
    FAULT_NONE,
    RUNAWAY_ABS_EVENT,
    RUNAWAY_FAULT_CODE,
    RUNAWAY_FAULT_STATE,
    RUNAWAY_RATE_EVENT,
    RUNAWAY_WILDCARD_EVENTS,
    ModelParseError,
    TransitionModel,
    build_model,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TEST_GEN_PATH = REPO_ROOT / "firmware" / "test" / "gen_transition_table.py"
GENERATED_HEADER_PATH = REPO_ROOT / "firmware" / "main" / "transition_table.h"

# Maps the test generator's bare wildcard event names to the model's
# canonical (EVENT_-prefixed) synthetic event names.
_TEST_WILDCARD_EVENT_TO_CANONICAL = {
    "RUNAWAY_ABSOLUTE_TEMP": RUNAWAY_ABS_EVENT,
    "RUNAWAY_RISE_RATE": RUNAWAY_RATE_EVENT,
}


class CrosscheckError(RuntimeError):
    """Raised for structural failures (can't load a source), not row drift."""


def _load_test_generator_module() -> ModuleType:
    """Import firmware/test/gen_transition_table.py as a module, without
    running its __main__ block, so its TRANSITIONS / ACTIVE_STATES lists
    can be read directly (read-only; never invokes --generate/--check)."""
    if not TEST_GEN_PATH.exists():
        raise CrosscheckError(f"test generator not found: {TEST_GEN_PATH}")
    spec = importlib.util.spec_from_file_location("gen_transition_table_testside", TEST_GEN_PATH)
    if spec is None or spec.loader is None:
        raise CrosscheckError(f"could not load spec for {TEST_GEN_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canonical_event(bare_event: str) -> str:
    if bare_event in _TEST_WILDCARD_EVENT_TO_CANONICAL:
        return _TEST_WILDCARD_EVENT_TO_CANONICAL[bare_event]
    return bare_event if bare_event.startswith("EVENT_") else f"EVENT_{bare_event}"


def _canonical_fault(fault) -> str:
    return fault if fault else FAULT_NONE


@dataclass
class RowDivergence:
    kind: str  # "missing_in_test" | "missing_in_production" | "value_mismatch"
    from_state: str
    event: str
    production: Tuple[str, str] | None = None  # (to, fault)
    test: Tuple[str, str] | None = None         # (to, fault)

    def describe(self) -> str:
        key = f"({self.from_state}, {self.event})"
        if self.kind == "missing_in_test":
            return f"{key}: production declares {self.production}, absent from test-side TRANSITIONS"
        if self.kind == "missing_in_production":
            return f"{key}: test-side TRANSITIONS declares {self.test}, absent from production manifest"
        return f"{key}: production={self.production} vs test-side={self.test}"


@dataclass
class CrosscheckReport:
    explicit_divergences: List[RowDivergence] = field(default_factory=list)
    wildcard_divergences: List[RowDivergence] = field(default_factory=list)
    wildcard_documented_exceptions: List[str] = field(default_factory=list)
    codegen_drift: List[str] = field(default_factory=list)
    production_row_count: int = 0
    test_row_count: int = 0

    @property
    def agrees(self) -> bool:
        return not (self.explicit_divergences or self.wildcard_divergences or self.codegen_drift)

    def to_dict(self) -> dict:
        return {
            "agrees": self.agrees,
            "production_row_count": self.production_row_count,
            "test_row_count": self.test_row_count,
            "explicit_divergences": [d.describe() for d in self.explicit_divergences],
            "wildcard_divergences": [d.describe() for d in self.wildcard_divergences],
            "wildcard_documented_exceptions_ktd2": self.wildcard_documented_exceptions,
            "codegen_drift": self.codegen_drift,
        }


def _production_explicit_rows(model: TransitionModel) -> Dict[Tuple[str, str], Tuple[str, str]]:
    return {
        (e.from_state, e.event): (e.to_state, e.fault)
        for e in model.explicit_edges()
    }


def _test_side_rows(test_module: ModuleType) -> Tuple[
    Dict[Tuple[str, str], Tuple[str, str]],   # non-wildcard rows
    Dict[Tuple[str, str], Tuple[str, str]],   # wildcard rows, expanded over ACTIVE_STATES
]:
    non_wildcard: Dict[Tuple[str, str], Tuple[str, str]] = {}
    wildcard: Dict[Tuple[str, str], Tuple[str, str]] = {}
    active_states = list(test_module.ACTIVE_STATES)

    for from_s, event, to_s, fault, _needs_setup in test_module.TRANSITIONS:
        canon_event = _canonical_event(event)
        canon_fault = _canonical_fault(fault)
        if from_s == "*":
            for active_state in active_states:
                wildcard[(active_state, canon_event)] = (to_s, canon_fault)
        else:
            non_wildcard[(from_s, canon_event)] = (to_s, canon_fault)

    return non_wildcard, wildcard


def crosscheck_explicit_rows(
    production_rows: Dict[Tuple[str, str], Tuple[str, str]],
    test_rows: Dict[Tuple[str, str], Tuple[str, str]],
) -> List[RowDivergence]:
    divergences: List[RowDivergence] = []
    all_keys = set(production_rows) | set(test_rows)
    for key in sorted(all_keys):
        from_s, event = key
        prod = production_rows.get(key)
        test = test_rows.get(key)
        if prod is not None and test is None:
            divergences.append(RowDivergence("missing_in_test", from_s, event, production=prod))
        elif prod is None and test is not None:
            divergences.append(RowDivergence("missing_in_production", from_s, event, test=test))
        elif prod != test:
            divergences.append(RowDivergence("value_mismatch", from_s, event, production=prod, test=test))
    return divergences


def crosscheck_wildcard_rows(
    model: TransitionModel,
    test_wildcard_rows: Dict[Tuple[str, str], Tuple[str, str]],
    active_states: List[str],
) -> Tuple[List[RowDivergence], List[str]]:
    """Compare the KTD2 implicit interlock edges against the test
    generator's wildcard-expanded rows. Values must agree on the overlap
    (``active_states``); the state-set difference is a documented
    exception, recorded but not an error."""
    divergences: List[RowDivergence] = []
    documented_exceptions: List[str] = []

    for state in model.states:
        for event in RUNAWAY_WILDCARD_EVENTS:
            key = (state, event)
            prod_edge = model.edges[key]  # implicit edge always present for every state
            prod_value = (prod_edge.to_state, prod_edge.fault)
            if state in active_states:
                test_value = test_wildcard_rows.get(key)
                if test_value is None:
                    divergences.append(RowDivergence(
                        "missing_in_test", state, event, production=prod_value))
                elif test_value != prod_value:
                    divergences.append(RowDivergence(
                        "value_mismatch", state, event, production=prod_value, test=test_value))
                # else: agrees, nothing to report
            else:
                documented_exceptions.append(
                    f"({state}, {event}) -> {prod_value}: present in the model (KTD2: all 9 "
                    f"states) but absent from the test generator's wildcard expansion "
                    f"(ACTIVE_STATES={sorted(active_states)}) -- documented state-set "
                    f"exception, not drift")

    # Also make sure the test side didn't declare a wildcard row for a
    # non-runaway event or a state outside model.states (would be a real
    # structural problem, not covered by the loop above).
    for (state, event), test_value in test_wildcard_rows.items():
        if event not in RUNAWAY_WILDCARD_EVENTS:
            divergences.append(RowDivergence(
                "missing_in_production", state, event, test=test_value))
        elif state not in model.states:
            divergences.append(RowDivergence(
                "missing_in_production", state, event, test=test_value))

    return divergences, documented_exceptions


def crosscheck_codegen_drift() -> List[str]:
    """Regenerate transition_table.h in memory from the production manifest
    and diff it against the committed file."""
    tools_dir = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "gen_transition_table_prodside", tools_dir / "gen_transition_table.py")
    if spec is None or spec.loader is None:
        raise CrosscheckError("could not load firmware/tools/gen_transition_table.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)

    header_path = REPO_ROOT / "firmware" / "main" / "state_machine.h"
    manifest_path = REPO_ROOT / "firmware" / "transition_table.yaml"
    template_path = tools_dir / "transition_table.h.j2"

    state_names, event_names, fault_names = gen.parse_state_machine_header(str(header_path))
    import yaml as _yaml
    manifest = _yaml.safe_load(manifest_path.read_text())
    transitions = manifest.get("transitions", [])

    val_errors = gen.validate_transitions(transitions, state_names, event_names, fault_names)
    if val_errors:
        raise CrosscheckError("manifest validation failed during codegen-drift check: " + "; ".join(val_errors))

    transition_cells = {}
    fault_cells = {}
    for row in transitions:
        key = (row["from"], row["event"])
        transition_cells[key] = row["to"]
        fault = row.get("fault")
        if fault:
            fault_cells[key] = fault

    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(str(template_path.parent)))
    template = env.get_template(template_path.name)
    rendered = template.render(
        state_names=state_names,
        event_names=event_names,
        transition_cells=transition_cells,
        fault_cells=fault_cells,
    )
    if not rendered.endswith("\n"):
        rendered += "\n"

    if not GENERATED_HEADER_PATH.exists():
        return [f"{GENERATED_HEADER_PATH} does not exist -- run gen_transition_table.py"]

    committed = GENERATED_HEADER_PATH.read_text()
    if committed != rendered:
        return [
            "firmware/main/transition_table.h is stale relative to "
            "firmware/transition_table.yaml -- run "
            "'python3 firmware/tools/gen_transition_table.py' and commit the result"
        ]
    return []


def run_crosscheck() -> CrosscheckReport:
    model = build_model()
    test_module = _load_test_generator_module()

    production_rows = _production_explicit_rows(model)
    test_non_wildcard, test_wildcard = _test_side_rows(test_module)

    explicit_divergences = crosscheck_explicit_rows(production_rows, test_non_wildcard)
    wildcard_divergences, documented_exceptions = crosscheck_wildcard_rows(
        model, test_wildcard, list(test_module.ACTIVE_STATES))
    codegen_drift = crosscheck_codegen_drift()

    return CrosscheckReport(
        explicit_divergences=explicit_divergences,
        wildcard_divergences=wildcard_divergences,
        wildcard_documented_exceptions=documented_exceptions,
        codegen_drift=codegen_drift,
        production_row_count=len(production_rows),
        test_row_count=len(test_non_wildcard) + len(test_wildcard),
    )


def main() -> int:
    try:
        report = run_crosscheck()
    except (ModelParseError, CrosscheckError) as exc:
        print(f"CROSSCHECK ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"production explicit rows: {report.production_row_count}")
    print(f"test-side rows (incl. wildcard-expanded): {report.test_row_count}")
    print(f"documented KTD2 state-set exceptions: {len(report.wildcard_documented_exceptions)}")

    if report.agrees:
        print("CROSSCHECK OK: manifests agree (modulo the documented KTD2 wildcard state-set exception)")
        return 0

    print("CROSSCHECK FAILED -- divergences found:", file=sys.stderr)
    for d in report.explicit_divergences:
        print(f"  [explicit] {d.describe()}", file=sys.stderr)
    for d in report.wildcard_divergences:
        print(f"  [wildcard] {d.describe()}", file=sys.stderr)
    for c in report.codegen_drift:
        print(f"  [codegen]  {c}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
