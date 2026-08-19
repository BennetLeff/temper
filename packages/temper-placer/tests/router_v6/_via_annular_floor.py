"""Fab-floor-compliant via geometry for ``router_v6`` tests, DERIVED from
the Rust owner of the floor rather than restated.

Why this module exists
----------------------
``temper-orchestration``'s ``Via::new``
(``packages/temper-orchestration/src/pipeline_route.rs``) enforces the
board's annular-ring fabrication floor AT CONSTRUCTION: a via whose pad
would leave a ring below ``MIN_ANNULAR_RING_MM`` is enlarged to the
board-wide ``ANNULAR_RING_TARGET_MM``-ring convention, drill untouched.
That clamp landed in **968d1a33d (PR #1316)**, "fix(router): enforce the
0.254mm annular floor in Via::new + drop co-located same-net vias".

Eight ``router_v6`` tests were still feeding that constructor a 0.6mm pad
on a 0.3mm drill -- a 0.15mm ring, well under the floor -- and asserting
0.6mm came back out. Because ``Via::new`` lives in a compiled extension,
those eight failed for anyone whose ``.so`` was current and passed for
anyone whose ``.so`` predated #1316: a suite whose verdict tracked build
state instead of code state, which cost several agents a session chasing
them as candidate regressions.

The durable fix is not new literals -- it is removing the literals. A
Python test that hardcodes a number Rust owns will rot the next time Rust
changes it. Everything here is read from the extension module at import
time; **this file contains no millimetre figure of its own**, and neither
should its callers.

Where the authority actually lives
----------------------------------
``MIN_ANNULAR_RING_MM`` is not a tunable. It is JLCPCB's 2oz-copper PTH
minimum, declared for this board in ``pcb/temper.kicad_pro`` as
``board.design_settings.rules.min_via_annular_width``, with the
``annular_width`` rule at severity ``error`` -- i.e. KiCad DRC rejects the
board outright below it. ``test_via_annular_floor_guard.py`` pins the Rust
constant to that board setting so the two cannot drift apart, and
``scripts/check_fact_registry_drift.py``'s ``min_via_annular_ring_mm``
fact enforces the same link mechanically in CI.

Usage
-----
Any fixture that hands via geometry to code which crosses the pyo3
boundary (``run_build_route_payload``, ``run_write_route_segments``, and
so the ``_write_routes_to_content`` shim) and then compares the result
against a NON-clamping Python oracle must feed a compliant pair, or the
differential reports the clamp as a divergence::

    from tests.router_v6._via_annular_floor import floor_compliant_via

    diameter, drill = floor_compliant_via()          # board Default class
    diameter, drill = floor_compliant_via(drill=0.4) # any other drill

Fixtures that deliberately exercise sub-floor geometry against a checker
(``test_annular_ring_boundary.py``, the DFM suites) are a different thing
entirely and must keep their literals -- they are testing detection of
bad rings, not round-tripping good ones.
"""

from __future__ import annotations

import temper_orchestration as _to

# The floor and the correction target, straight from the crate that
# enforces them. Re-exported (not re-declared) so callers can import them
# from one place; `AttributeError` here means the extension predates
# #1316's export and the caller's measurement would be meaningless --
# exactly the failure `scripts/check_stale_extensions.py` exists to catch,
# surfaced loudly at import instead of as a mystery numeric diff.
MIN_ANNULAR_RING_MM: float = _to.MIN_ANNULAR_RING_MM
ANNULAR_RING_TARGET_MM: float = _to.ANNULAR_RING_TARGET_MM

# The drill this project's "Default" net class uses (pcb/temper.kicad_pro:
# via_drill 0.3). `Via::new` NEVER touches drill -- the clamp is a pad-
# geometry correction, not a current-capacity change -- so drill is a free
# fixture choice, not a Rust-owned constant, and naming it here is not the
# hardcoding this module exists to avoid.
DEFAULT_VIA_DRILL_MM: float = 0.3


def floor_compliant_diameter(drill: float = DEFAULT_VIA_DRILL_MM) -> float:
    """The pad diameter ``Via::new`` corrects a sub-floor via TO.

    Mirrors the crate's own arithmetic (``drill + 2 * target``) in Python,
    on the crate's own constant -- so it is a fixed point of the clamp
    without being a copy of the clamp's output.
    """
    return drill + 2.0 * ANNULAR_RING_TARGET_MM


def floor_compliant_via(drill: float = DEFAULT_VIA_DRILL_MM) -> tuple[float, float]:
    """``(diameter, drill)`` that ``Via::new`` passes through untouched."""
    return floor_compliant_diameter(drill), drill


def is_floor_compliant(diameter: float, drill: float) -> bool:
    """Would ``Via::new`` leave this pair alone?

    The predicate is the crate's, negated: ``Via::new`` clamps when
    ``diameter - drill < 2 * MIN_ANNULAR_RING_MM``.
    """
    return (diameter - drill) >= 2.0 * MIN_ANNULAR_RING_MM
