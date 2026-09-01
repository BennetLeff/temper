"""The via annular-ring fab floor, pinned from the Python side.

Why this file exists
--------------------
968d1a33d (PR #1316) made ``temper-orchestration``'s ``Via::new`` enforce
the board's annular-ring fabrication floor at construction. The change was
correct and is not in question here. What it also did was leave eight
Python ``router_v6`` tests holding the pre-floor 0.6mm pad literal, with
nothing in the repo connecting the two sides: the Rust constant moved, the
Python expectations did not, and because the constant lives in a compiled
extension the eight tests **passed or failed according to when the reader
last ran ``maturin develop``**. Several agents lost time chasing them as
candidate regressions before anyone noticed the verdict was tracking build
state rather than code state.

This file is the connection those eight tests were missing. It does three
distinct jobs, none of which is "assert 0.9":

1. **The floor is reachable from Python at all.** ``Via::new``'s constants
   are exported (``temper_orchestration.MIN_ANNULAR_RING_MM`` /
   ``ANNULAR_RING_TARGET_MM``), which is what lets
   ``tests/router_v6/_via_annular_floor.py`` derive fixture geometry
   instead of restating it. If the export disappears, every derived
   fixture fails loudly at import rather than silently reverting to a
   literal.
2. **The Rust floor matches the fabricator's floor.** The authority is not
   this crate: it is ``pcb/temper.kicad_pro``'s
   ``board.design_settings.rules.min_via_annular_width``, the figure KiCad
   DRC enforces at severity ``error``. The two are pinned to each other here,
   so neither can be edited alone.
3. **The clamp still clamps, and still leaves compliant pads alone.**
   Asserted at the real pyo3 boundary and end to end through the writer,
   with every expected number derived from (1). If the clamp is ever
   removed, weakened, or retargeted, THIS test says so in one line naming
   the commit — instead of eight marshalling differentials reporting
   byte-diffs that read like a router regression.

Anti-vacuity (measured 2026-08-18, not asserted)
------------------------------------------------
Verified failing against the pre-fix state, not merely passing against the
fixed one. Both experiments were run in this worktree with all 10 pyo3
crates reported fresh by ``scripts/check_stale_extensions.py``, and both
were reverted afterwards.

**1. Clamp neutralised in ``Via::new``**, extension rebuilt --
``4 failed, 6 passed``::

    test_subfloor_pad_is_corrected_at_the_pyo3_boundary[0.3]
    E   AssertionError: `Via::new` did not enlarge a 0.2290mm-ring pad to
    E   the 0.3mm-ring convention. ...
    E   assert 0.758 == 0.8999999999999999 +- 9.0e-07

    test_subfloor_pad_is_corrected_end_to_end_through_the_writer
    E   AssertionError: the emitted (via ...) must carry the corrected pad,
    E   not the sub-floor one it was handed -- got:
    E     (via (at 2.5000 0.0000) (size 0.7580) (drill 0.3000) ...)
    E   assert '(size 0.9000)' in '... (size 0.7580) ...'

The same clamp-less build is also what pins the diagnosis this file
records: with it installed, all 76 tests in the three PRE-FIX files
(``test_adapter_convert_marshal_rust_differential.py``,
``test_pipeline_route_rust_differential.py``,
``test_via_output_writer.py``) pass -- the same 76 that produce 8 failures
against a build that has the clamp. That is the build-state-dependent
verdict in one measurement, and it is why those eight were stale rather
than the crate being wrong.

**2. ``MIN_ANNULAR_RING_MM`` perturbed to 0.3**, extension rebuilt --
``3 failed, 7 passed``::

    test_rust_floor_matches_the_board_fab_setting
    E   AssertionError: Rust's annular floor (0.3) and the board's
    E   min_via_annular_width (0.254) have drifted apart. ...
    E   assert 0.254 == 0.3

    test_compliant_pad_is_a_fixed_point_of_the_clamp[0.3]
    test_subfloor_pad_is_corrected_at_the_pyo3_boundary[0.3]
    E   assert False
    E    +  where False = is_floor_compliant(0.8999999999999999, 0.3)

The same perturbation is caught mechanically outside pytest, by
``scripts/check_fact_registry_drift.py``'s ``min_via_annular_ring_mm``
fact (registered with this change)::

    OK    pcb/temper.kicad_pro (board DRC rule min_via_annular_width): 0.254
    DIFF  packages/temper-orchestration/src/pipeline_route.rs (...): 0.3

The fixed-point test is the one that keeps the eight repaired fixtures
honest: it asserts the exact pair
``_via_annular_floor.floor_compliant_via()`` hands out survives the clamp
unchanged, so if the crate ever retargets the correction the derived
fixtures move with it and this test proves they still round-trip.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import temper_orchestration as _to

from temper_placer.router_v6.adapter import _write_routes_to_content
from tests.router_v6._via_annular_floor import (
    ANNULAR_RING_TARGET_MM,
    MIN_ANNULAR_RING_MM,
    floor_compliant_via,
    is_floor_compliant,
)

# `pcb/` sits at the repo root; this file is
# packages/temper-placer/tests/router_v6/.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_KICAD_PRO = _REPO_ROOT / "pcb" / "temper.kicad_pro"


# ---------------------------------------------------------------------------
# 1. The floor is reachable from Python
# ---------------------------------------------------------------------------


def test_floor_constants_are_exported_from_the_crate() -> None:
    """Both constants must be importable floats.

    This is the backstop for everything below and for every derived
    fixture: if the export is gone, the tests that consume it must fail
    at import, not quietly fall back to a hardcoded number.
    """
    assert isinstance(_to.MIN_ANNULAR_RING_MM, float)
    assert isinstance(_to.ANNULAR_RING_TARGET_MM, float)
    # The helper module must re-export, not re-declare.
    assert MIN_ANNULAR_RING_MM == _to.MIN_ANNULAR_RING_MM
    assert ANNULAR_RING_TARGET_MM == _to.ANNULAR_RING_TARGET_MM
    # A correction target below the floor it corrects to would be
    # self-defeating -- the clamp would produce pads it would clamp again.
    assert ANNULAR_RING_TARGET_MM >= MIN_ANNULAR_RING_MM


# ---------------------------------------------------------------------------
# 2. The Rust floor is the fabricator's floor
# ---------------------------------------------------------------------------


def test_rust_floor_matches_the_board_fab_setting() -> None:
    """``Via::new``'s floor and the board's DRC setting are one fact.

    ``MIN_ANNULAR_RING_MM`` is not this crate's opinion. It is JLCPCB's
    2oz-copper PTH minimum as declared for this board, and KiCad enforces
    it at severity ``error`` -- a board below it does not fabricate. The
    crate enforcing a DIFFERENT number than the board declares is the
    silent-divergence shape this whole file exists to prevent, so the two
    are pinned together.
    """
    assert _KICAD_PRO.is_file(), f"board project file missing: {_KICAD_PRO}"
    settings = json.loads(_KICAD_PRO.read_text())["board"]["design_settings"]["rules"]
    assert "min_via_annular_width" in settings, (
        "the board project no longer declares min_via_annular_width -- the "
        "scan can no longer confirm the crate agrees with the fabricator, "
        "which is a tool error, not a pass"
    )
    board_floor = float(settings["min_via_annular_width"])
    assert board_floor == MIN_ANNULAR_RING_MM, (
        f"Rust's annular floor ({MIN_ANNULAR_RING_MM}) and the board's "
        f"min_via_annular_width ({board_floor}) have drifted apart. Neither "
        f"is a tunable: fix whichever one moved, do not reconcile by "
        f"lowering the floor. See pipeline_route.rs::MIN_ANNULAR_RING_MM "
        f"and pcb/temper.kicad_pro."
    )


def test_board_enforces_the_annular_rule_as_an_error() -> None:
    """A floor KiCad only warns about would not be a floor.

    The severity is what makes ``Via::new``'s clamp load-bearing rather
    than cosmetic, so it is part of the fact being pinned.
    """
    rules = json.loads(_KICAD_PRO.read_text())["board"]["design_settings"]["rule_severities"]
    assert rules.get("annular_width") == "error", (
        f"annular_width severity is {rules.get('annular_width')!r}, not "
        f"'error' -- the fab floor Via::new enforces is no longer enforced "
        f"by the board's own DRC"
    )


# ---------------------------------------------------------------------------
# 3. The clamp behaves, with every expectation derived
# ---------------------------------------------------------------------------


def _payload_vias(vias: list) -> list:
    """Drive one route's vias through the real pyo3 marshalling."""
    path = SimpleNamespace(path_length=0.0, coordinates=[])
    route = SimpleNamespace(path=path, width_mm=0.2, vias=list(vias))
    return _to.run_build_route_payload(path, route, "NET1", 1, 0)[5]


def _via(diameter: float, drill: float) -> SimpleNamespace:
    return SimpleNamespace(
        position=(1.0, 2.0),
        diameter=diameter,
        drill=drill,
        from_layer="F.Cu",
        to_layer="B.Cu",
    )


@pytest.mark.parametrize("drill", [0.3, 0.4, 0.5])
def test_subfloor_pad_is_corrected_at_the_pyo3_boundary(drill: float) -> None:
    """A pad below the floor comes back enlarged to the target ring.

    The sub-floor input is built by walking DOWN from the floor rather
    than by naming a number, so this stays a test of the clamp and not of
    one historical via size.
    """
    subfloor_diameter = drill + 2.0 * MIN_ANNULAR_RING_MM - 0.05
    assert not is_floor_compliant(subfloor_diameter, drill), "fixture is not sub-floor"

    want_diameter = drill + 2.0 * ANNULAR_RING_TARGET_MM
    (got,) = _payload_vias([_via(subfloor_diameter, drill)])

    assert got[2] == pytest.approx(want_diameter), (
        f"`Via::new` did not enlarge a "
        f"{(subfloor_diameter - drill) / 2:.4f}mm-ring pad to the "
        f"{ANNULAR_RING_TARGET_MM}mm-ring convention. This clamp is the "
        f"fab-floor enforcement added in 968d1a33d (PR #1316); if it has "
        f"been removed, the board can be routed with unfabricable vias "
        f"again (56 of them, the last time)."
    )
    assert got[3] == pytest.approx(drill), (
        "the clamp is a PAD-geometry correction -- drill must be untouched, "
        "or it would silently change the via's current capacity"
    )
    assert is_floor_compliant(got[2], got[3])


@pytest.mark.parametrize("drill", [0.3, 0.4, 0.5])
def test_compliant_pad_is_a_fixed_point_of_the_clamp(drill: float) -> None:
    """The pad the shared fixture helper hands out survives untouched.

    This is what keeps the eight repaired ``router_v6`` fixtures honest.
    They feed ``floor_compliant_via()`` into differentials whose pinned
    Python oracles do NOT clamp; that only stays valid while the pair the
    helper produces is a fixed point of ``Via::new``. If the crate ever
    retargets the correction, the helper follows it and this test proves
    the differentials still round-trip -- no silent drift, either way.
    """
    diameter, got_drill = floor_compliant_via(drill=drill)
    assert got_drill == drill
    assert is_floor_compliant(diameter, drill)

    (got,) = _payload_vias([_via(diameter, drill)])
    assert got[2] == diameter, (
        "a fab-floor-compliant pad must pass through `Via::new` unchanged; "
        "tests/router_v6/_via_annular_floor.py's derivation and the crate's "
        "clamp have diverged"
    )
    assert got[3] == drill


def test_subfloor_pad_is_corrected_end_to_end_through_the_writer() -> None:
    """The correction survives all the way into the emitted s-expression.

    The clamp is only worth anything if the ``(via ...)`` KiCad actually
    reads carries the corrected pad, so this drives the production shim
    (``_write_routes_to_content``) rather than the marshalling call alone.
    """
    from temper_placer.router_v6.astar_core import RoutePath

    drill = 0.3
    subfloor_diameter = drill + 2.0 * MIN_ANNULAR_RING_MM - 0.05
    assert not is_floor_compliant(subfloor_diameter, drill), "fixture is not sub-floor"

    via = SimpleNamespace(
        position=(2.5, 0.0),
        from_layer="F.Cu",
        to_layer="B.Cu",
        diameter=subfloor_diameter,
        drill=drill,
        net_name="NET",
    )
    path = RoutePath(
        net_name="NET",
        coordinates=[(0, 0), (5, 0), (10, 0)],
        layer_name="F.Cu",
        path_length=10.0,
    )
    comps = []
    for idx, pos in enumerate([(0.0, 0.0), (10.0, 0.0)]):
        c = SimpleNamespace(ref=f"C{idx}", initial_position=pos)
        c.get_pin = lambda _name: SimpleNamespace(position=(0.0, 0.0))
        comps.append(c)
    result = SimpleNamespace(
        stage4=SimpleNamespace(
            routing_results=SimpleNamespace(
                compiled_routes={
                    "NET": SimpleNamespace(
                        net_name="NET", path=path, width_mm=0.25, vias=[via]
                    )
                },
                partial_routes={},
                tree_routes={},
                partial_tree_routes={},
            )
        ),
        pcb=SimpleNamespace(
            components=comps,
            nets=[SimpleNamespace(name="NET", pins=[(c.ref, "1") for c in comps])],
        ),
    )

    content = _write_routes_to_content('(kicad_pcb\n  (net 1 "NET")\n)\n', result)[0]
    want_diameter = drill + 2.0 * ANNULAR_RING_TARGET_MM
    assert f"(size {want_diameter:.4f})" in content, (
        f"the emitted (via ...) must carry the corrected pad, not the "
        f"sub-floor one it was handed -- got:\n{content}"
    )
    assert f"(size {subfloor_diameter:.4f})" not in content
    assert f"(drill {drill:.4f})" in content, "drill must be emitted untouched"
