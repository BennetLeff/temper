#!/usr/bin/env python3
"""IPC-2221B current-derived trace-width floor gate.

WHY THIS EXISTS
---------------
PR #1187 fixed the hyphen-boundary defect that had `hb-gnd` (the
half-bridge low-side switch return, ~10-22.5A RMS -- see
`packages/temper-geometry/src/ipc2221b_current_width.rs` for the full
current derivation) falling through to `determine_trace_width`'s 0.127mm
"standard signal trace" default. That fix took it to 0.508mm -- a real,
necessary 4x improvement, but still 3x-9x short of the 1.56-4.77mm this
repo's own IPC-2221B method (`docs/hardware/TRACE_WIDTH_CALCULATIONS.md`)
requires for that current, because `determine_trace_width` is a pure
function of the net NAME and has no vocabulary for "this net carries 22A".

The follow-up fix made `assign_trace_widths` (the production Stage 4.4/4.5
router entrypoint, `_pipeline_route.py:674`) call
`_determine_trace_width_ipc_aware` instead of the keyword-only
`_determine_trace_width` -- which widens (never narrows) the keyword-bucket
width to the IPC-2221B current-derived floor for any net registered in
`temper_geometry`'s `ipc2221b_current_width::KNOWN_NET_CURRENTS`.

This gate is the fail-closed regression check for that wiring: for every
net in the current registry, it re-derives the IPC-2221B requirement
independently (from the registry's own declared current/temp-rise/copper
figures) and asserts that the width the PRODUCTION entrypoint
(`assign_trace_widths`, called via a synthetic `PathfindingResult`, not
the low-level function directly) actually assigns is at or above that
requirement. A regression that reverts the wiring (e.g. a merge that
restores the plain `_determine_trace_width` call) or that shrinks
`power_width`/`hv_width` below a net's IPC floor is caught here, not
discovered at DRC time or later.

An empty registry (`KNOWN_NET_CURRENTS` regressed to zero entries) is
itself treated as a violation -- a gate with nothing to check would pass
silently forever, which is exactly the failure mode PR #1138 exists to
prevent ("a gate was wired into CI unregistered"; the analogous failure
here would be a gate registered but checking nothing).

Never `continue-on-error`: a gate that cannot run must exit non-zero.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

# Production defaults, mirroring
# `packages/temper-placer/src/temper_placer/router_v6/_pipeline_route.py`'s
# `assign_trace_widths(pathfinding_result, default_width=pcb.design_rules.
# default_trace_width_mm)` call -- only `default_width` is threaded through
# there; `power_width`/`hv_width` fall back to
# `trace_width_assignment.py`'s own defaults, reproduced here so this gate
# checks what production actually assigns, not a hypothetical.
_DEFAULT_WIDTH_MM = 0.127
_POWER_WIDTH_MM = 0.508
_HV_WIDTH_MM = 0.635


@dataclass(frozen=True)
class Violation:
    net_name: str
    assigned_width_mm: float
    required_width_mm: float
    current_a: float


def find_violations(
    default_width: float = _DEFAULT_WIDTH_MM,
    power_width: float = _POWER_WIDTH_MM,
    hv_width: float = _HV_WIDTH_MM,
    assign_fn=None,
) -> tuple[list[Violation], list[str]]:
    """Check every registered net's PRODUCTION-assigned width against its
    independently-recomputed IPC-2221B requirement.

    Returns ``(violations, registered_net_names)``. Exercises the real
    production entrypoint (`assign_trace_widths`, via a synthetic
    `PathfindingResult`) rather than calling the low-level Rust function
    directly, so a wiring regression in `trace_width_assignment.py` or
    `_pipeline_route.py` is caught here too, not just a formula regression.

    ``assign_fn`` defaults to the real production
    ``trace_width_assignment.assign_trace_widths``; tests inject a
    substitute (e.g. one wired to the pre-fix, keyword-only
    ``_determine_trace_width``) to prove this gate actually catches a
    reverted-wiring regression -- see
    ``scripts/tests/test_check_ipc2221b_trace_width_floor.py``.
    """
    import temper_geometry as tg
    from temper_placer.router_v6._routing_reports import PathfindingResult

    if assign_fn is None:
        from temper_placer.router_v6.trace_width_assignment import assign_trace_widths as assign_fn

    net_names = tg.known_net_current_names_py()

    # Exercise the production orchestration entrypoint exactly as
    # `_pipeline_route.py` does: a `PathfindingResult` whose `routed_paths`
    # keys are the net names the router laid copper for. The trace-width
    # step only reads dict keys (not path geometry), so a sentinel value
    # is sufficient here -- see `assign_trace_widths`'s body.
    result = PathfindingResult(routed_paths={name: None for name in net_names}, failed_nets=[])
    width_assignment = assign_fn(
        result,
        default_width=default_width,
        power_width=power_width,
        hv_width=hv_width,
    )

    violations: list[Violation] = []
    for net_name in net_names:
        entry = tg.known_net_current_py(net_name)
        if entry is None:
            # Registry drift between known_net_current_names_py and
            # known_net_current_py would itself be a bug in the Rust
            # module, not something this gate can compute a requirement
            # for -- treat as a violation rather than silently skipping.
            violations.append(Violation(net_name, float("nan"), float("nan"), float("nan")))
            continue
        current_a_low, current_a_high, temp_rise_c, copper_oz, internal_layer, _source = entry
        required = tg.ipc2221b_required_width_mm_py(current_a_high, temp_rise_c, copper_oz, internal_layer)
        assigned = width_assignment.get_width(net_name)
        if assigned is None or assigned < required:
            violations.append(Violation(net_name, assigned if assigned is not None else float("nan"), required, current_a_high))

    return violations, net_names


def main() -> int:
    try:
        violations, net_names = find_violations()
    except Exception as exc:  # pylint: disable=broad-except
        print(f"[check_ipc2221b_trace_width_floor] GATE ERROR: {exc}", file=sys.stderr)
        return EXIT_GATE_ERROR

    if not net_names:
        print(
            "[check_ipc2221b_trace_width_floor] GATE ERROR: "
            "ipc2221b_current_width::KNOWN_NET_CURRENTS is empty -- this gate "
            "has nothing to check, which is itself a regression (a current-"
            "derived-width registry with zero entries defeats the point of "
            "this gate). Fix: re-register hb-gnd (or any net whose current "
            "is derivable from elec/src) in "
            "packages/temper-geometry/src/ipc2221b_current_width.rs.",
            file=sys.stderr,
        )
        return EXIT_VIOLATION

    print(f"[check_ipc2221b_trace_width_floor] {len(net_names)} registered net(s) checked: {net_names}")

    state = "clean"
    if violations:
        state = "violation"
        print(
            f"[check_ipc2221b_trace_width_floor] FAIL -- {len(violations)} net(s) "
            "assigned a trace width below their IPC-2221B current-derived requirement:",
            file=sys.stderr,
        )
        for v in violations:
            print(
                f"  - {v.net_name}: assigned={v.assigned_width_mm:.4f}mm, "
                f"required={v.required_width_mm:.4f}mm (at {v.current_a:.2f}A)",
                file=sys.stderr,
            )
    else:
        print("[check_ipc2221b_trace_width_floor] PASS -- every registered net meets its IPC-2221B floor.")

    summary_path = get_github_summary_path()
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(f"\n### IPC-2221B Trace Width Floor Gate: {state}\n")
            f.write(f"- Registered nets checked: {len(net_names)}\n")
            f.write(f"- Violations: {len(violations)}\n")
            if violations:
                f.write("\nViolations:\n")
                for v in violations:
                    f.write(
                        f"- `{v.net_name}`: assigned={v.assigned_width_mm:.4f}mm, "
                        f"required={v.required_width_mm:.4f}mm (at {v.current_a:.2f}A)\n"
                    )

    if violations:
        return EXIT_VIOLATION
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
