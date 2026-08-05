"""Differential test: preflight decision kernels in Rust
(temper_design_bundle_python.validation) vs the pinned Python oracle
(Wave 4, Phase 4 — validation remainder slice).

``temper_placer/validation/preflight.py`` moves its DECISION compute —
the zone AABB checks (``_zones_overlap``, the zone-fit boundary checks and
reason-string selection), the have-zones set arithmetic, and the
impossible-constraints bounds/set checks — to Rust kernels in the
``validation`` submodule of ``temper_design_bundle_python``. The Python
module keeps the dataclasses (``PreflightIssue``/``PreflightResult``/
``PreflightSeverity``), the tool-availability checks (``shutil.which`` /
``find_kicad_cli`` are I/O boundaries), the netlist<->board reconciliation
check (an orchestration over the reconciliation surface, itself migrated),
and message assembly wherever a no-format ``str(float)`` interpolation is
involved (``ZONE_003``'s suggestion and ``ZONE_005``'s message — Rust
``Display`` renders ``10.0`` as ``10``; CPython renders ``10.0``). The
pre-migration module is pinned verbatim as the oracle
(``_preflight_py_oracle.py``).

Comparison convention: the full ``PreflightResult`` (issue lists, messages,
suggestions, components, details) is compared through a canonicalizer that
carries each leaf's concrete type and renders floats via ``float.hex()`` —
the messages derive from the Rust-returned decisions, so a mutation in a
decision or a message is caught.

Sections:
- Differential bit-exactness (hand-built + random constraint shapes).
- PBT (hypothesis): five non-vacuous properties.
- Metamorphic relations: three, honestly bounded.
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb
from hypothesis import given, settings
from hypothesis import strategies as st

import tests.validation._preflight_py_oracle as _oracle
from temper_placer.core.board import Zone
from temper_placer.core.netlist import Component, Netlist
from temper_placer.io.config_loader import (
    ComponentGroup,
    PlacementConstraints,
    ThermalConstraint,
)
from temper_placer.validation.preflight import (
    PreflightIssue,
    PreflightResult,
    PreflightSeverity,
)
from temper_placer.validation.preflight import (
    _zones_overlap as shim_zones_overlap,  # noqa: E402
)
from temper_placer.validation.preflight import (
    check_components_have_zones as shim_components_have_zones,  # noqa: E402
)
from temper_placer.validation.preflight import (
    check_impossible_constraints as shim_impossible_constraints,  # noqa: E402
)
from temper_placer.validation.preflight import (
    check_zones_fit_on_board as shim_zones_fit,  # noqa: E402
)

# Rust symbols under test — must exist or this file fails to collect (RED).
ZONES_OVERLAP = _tdb.validation.zones_overlap
PREFLIGHT_ZONES_FIT = _tdb.validation.preflight_zones_fit
PREFLIGHT_UNASSIGNED = _tdb.validation.preflight_unassigned
PREFLIGHT_IMPOSSIBLE = _tdb.validation.preflight_impossible

# ---------------------------------------------------------------------------
# Canonicalization
# ---------------------------------------------------------------------------


def _canon_value(v):
    """Carry each leaf's concrete type; floats via .hex()."""
    if isinstance(v, float):
        return ("float", v.hex())
    if isinstance(v, int) and not isinstance(v, bool):
        return ("int", v)
    if isinstance(v, bool):
        return ("bool", v)
    if isinstance(v, str):
        return ("str", v)
    if isinstance(v, tuple):
        return ("tuple", tuple(_canon_value(x) for x in v))
    if isinstance(v, list):
        return ("list", [_canon_value(x) for x in v])
    if isinstance(v, dict):
        return ("dict", tuple(sorted((k, _canon_value(x)) for k, x in v.items())))
    return ("obj", type(v).__name__, repr(v))


def _canon_issue(i: PreflightIssue) -> tuple:
    return (
        i.severity.name,
        i.code,
        i.message,
        i.suggestion,
        tuple(i.components),
        _canon_value(i.details),
    )


def _canon_result(r: PreflightResult) -> tuple:
    return (r.passed, tuple(_canon_issue(i) for i in r.issues))


# ---------------------------------------------------------------------------
# Input construction
# ---------------------------------------------------------------------------

_COORD = st.floats(min_value=-500.0, max_value=1500.0, allow_nan=False, allow_infinity=False)
_MM = st.floats(min_value=0.0, max_value=500.0, allow_nan=False, allow_infinity=False)
# Board dimensions must be strictly positive (PlacementConstraints).
_BOARD_MM = st.floats(
    min_value=0.1, max_value=500.0, allow_nan=False, allow_infinity=False
)
_REF = st.text(min_size=1, max_size=6).map(lambda s: f"C{abs(hash(s)) % 1999}")
_BOUNDS = st.tuples(_COORD, _COORD, _COORD, _COORD).filter(
    lambda b: b[2] > b[0] and b[3] > b[1]
)
# A zone fully inside a 2000x2000 board (used by prop2) — x/y pairs are
# drawn independently with a light strict-increase filter (no degenerate
# rectangles; the Rect contract rejects x_max == x_min).
_IN_BOARD_BOUNDS = st.tuples(
    st.floats(min_value=0.0, max_value=990.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=990.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
).filter(lambda b: b[2] > b[0] and b[3] > b[1])


def _constraints(
    zones: list[tuple[str, tuple[float, float, float, float], list[str]]],
    *,
    board_w: float = 100.0,
    board_h: float = 100.0,
    assignments: dict[str, str] | None = None,
    groups: list[tuple[str, str | None, list[str]]] | None = None,
    fixed: list[str] | None = None,
    thermals: list[list[str]] | None = None,
) -> PlacementConstraints:
    return PlacementConstraints(
        board_width_mm=board_w,
        board_height_mm=board_h,
        board_margin_mm=3.0,
        zones=[
            Zone(name=name, bounds=bounds, net_classes=["Signal"], components=comps)
            for name, bounds, comps in zones
        ],
        zone_assignments=assignments or {},
        component_groups=[
            ComponentGroup(name=name, components=comps, zone=zone) if zone is not None
            else ComponentGroup(name=name, components=comps)
            for name, zone, comps in groups or []
        ],
        fixed_components=fixed or [],
        thermal_constraints=[
            ThermalConstraint(components=comps) for comps in (thermals or [])
        ],
    )


def _netlist(components: list[tuple[str, tuple[float, float]]]) -> Netlist:
    return Netlist(
        components=[
            Component(ref=ref, footprint="fp", bounds=bounds) for ref, bounds in components
        ],
        nets=[],
    )


def _run_zones_fit_both(constraints: PlacementConstraints):
    return (
        _canon_result(_oracle.check_zones_fit_on_board(constraints)),
        _canon_result(shim_zones_fit(constraints)),
    )


def _run_have_zones_both(netlist: Netlist, constraints: PlacementConstraints, require_all: bool):
    return (
        _canon_result(_oracle.check_components_have_zones(netlist, constraints, require_all)),
        _canon_result(shim_components_have_zones(netlist, constraints, require_all)),
    )


def _run_impossible_both(netlist: Netlist, constraints: PlacementConstraints):
    return (
        _canon_result(_oracle.check_impossible_constraints(netlist, constraints)),
        _canon_result(shim_impossible_constraints(netlist, constraints)),
    )


# ---------------------------------------------------------------------------
# Differential — zones fit on board
# ---------------------------------------------------------------------------


def test_zones_overlap_kernel_matches_helper():
    """The Rust AABB kernel agrees with the oracle's ``_zones_overlap`` on
    the classic overlap/edge-touch/disjoint cases."""
    cases = [
        ((0, 0, 50, 50), (25, 25, 75, 75), True),
        ((0, 0, 50, 50), (100, 0, 150, 50), False),
        ((0, 0, 50, 50), (50, 0, 100, 50), False),  # edge-touch: no overlap
        ((0, 0, 50, 50), (0, 50, 50, 100), False),  # edge-touch on y
        ((0, 0, 50, 50), (0, 0, 50, 50), True),  # identical
        ((-10, -10, 10, 10), (0, 0, 5, 5), True),  # containment
    ]
    for a, b, expected in cases:
        oa = _oracle._zones_overlap(Zone(name="A", bounds=a, net_classes=[], components=[]),
                                    Zone(name="B", bounds=b, net_classes=[], components=[]))
        shim = shim_zones_overlap(Zone(name="A", bounds=a, net_classes=[], components=[]),
                                  Zone(name="B", bounds=b, net_classes=[], components=[]))
        assert shim is expected, (a, b)
        assert oa is expected, (a, b)


@settings(max_examples=60, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.text(min_size=1, max_size=6).map(lambda s: f"Z{abs(hash(s)) % 97}"),
            _BOUNDS,
            st.lists(_REF, min_size=0, max_size=3),
        ),
        min_size=0,
        max_size=6,
    ),
    _BOARD_MM,
    _BOARD_MM,
)
def test_zones_fit_differential_random(zones, board_w, board_h):
    constraints = _constraints(zones, board_w=board_w, board_h=board_h)
    oracle, shim = _run_zones_fit_both(constraints)
    assert shim == oracle


def test_zones_fit_differential_hand_built():
    """Every ZONE_003 reason variant, the overlap warning, and the empty /
    clean paths."""
    cases = [
        # clean fit -> ZONE_005 info
        ([("A", (0, 0, 50, 50), [])], 100.0, 100.0),
        # x_max over
        ([("W", (0, 0, 150, 50), [])], 100.0, 100.0),
        # y_max over
        ([("H", (0, 0, 50, 150), [])], 100.0, 100.0),
        # x_min negative
        ([("N", (-10, 0, 50, 50), [])], 100.0, 100.0),
        # y_min negative
        ([("N", (0, -10, 50, 50), [])], 100.0, 100.0),
        # multiple reasons on one zone
        ([("B", (-5, -5, 105, 105), [])], 100.0, 100.0),
        # two outside zones, both reported, in zone order
        ([("A", (-5, 0, 50, 50), []), ("B", (0, 0, 150, 50), [])], 100.0, 100.0),
        # overlapping zones -> ZONE_004 warning + clean -> no ZONE_005
        ([("A", (0, 0, 60, 60), []), ("B", (40, 40, 100, 100), [])], 100.0, 100.0),
        # no zones at all -> ZONE_005 with 0
        ([], 100.0, 100.0),
        # non-multiple-of-10 board with awkward floats (message formatting)
        ([("F", (0.5, 0.25, 49.75, 49.5), [])], 50.125, 50.125),
    ]
    for zones, bw, bh in cases:
        constraints = _constraints(zones, board_w=bw, board_h=bh)
        oracle, shim = _run_zones_fit_both(constraints)
        assert shim == oracle, (zones, bw, bh, oracle, shim)


# ---------------------------------------------------------------------------
# Differential — components have zones
# ---------------------------------------------------------------------------


@settings(max_examples=60, deadline=None)
@given(
    st.lists(_REF, min_size=0, max_size=10),
    st.lists(_REF, min_size=0, max_size=10),
    st.lists(_REF, min_size=0, max_size=10),
    st.booleans(),
)
def test_have_zones_differential_random(netlist_refs, assigned, fixed, require_all):
    netlist = _netlist([(r, (1.0, 1.0)) for r in netlist_refs])
    constraints = _constraints(
        [("Z", (0, 0, 50, 50), assigned)],
        assignments={},
        fixed=fixed,
    )
    oracle, shim = _run_have_zones_both(netlist, constraints, require_all)
    assert shim == oracle


def test_have_zones_differential_hand_built():
    # All assigned (some via zones, some via assignments, some via groups).
    netlist = _netlist([("R1", (1.0, 1.0)), ("D1", (1.0, 1.0)), ("J1", (1.0, 1.0))])
    constraints = _constraints(
        [("Z", (0, 0, 50, 50), ["R1"])],
        assignments={"D1": "Z"},
        groups=[("g", "Z", ["J1"])],
    )
    oracle, shim = _run_have_zones_both(netlist, constraints, require_all=True)
    assert shim == oracle
    assert shim[0] is True  # passed

    # Unassigned with require_all=False -> WARNING ZONE_001, passed=True.
    constraints = _constraints([("Z", (0, 0, 50, 50), ["R1"])])
    oracle, shim = _run_have_zones_both(netlist, constraints, require_all=False)
    assert shim == oracle
    issues = shim[1]
    assert issues[0][1] == "ZONE_001"
    assert issues[0][0] == "WARNING"
    assert shim[0] is True

    # Unassigned with require_all=True -> ERROR ZONE_001, passed=False.
    oracle, shim = _run_have_zones_both(netlist, constraints, require_all=True)
    assert shim == oracle
    assert shim[0] is False
    assert shim[1][0][0] == "ERROR"

    # Fixed components exempt.
    constraints = _constraints(
        [("Z", (0, 0, 50, 50), ["R1"])], fixed=["D1", "J1"]
    )
    oracle, shim = _run_have_zones_both(netlist, constraints, require_all=True)
    assert shim == oracle
    assert shim[0] is True

    # >10 unassigned -> the "+N more..." truncation branch.
    refs = [f"U{i}" for i in range(15)]
    netlist = _netlist([(r, (1.0, 1.0)) for r in refs])
    constraints = _constraints([])
    oracle, shim = _run_have_zones_both(netlist, constraints, require_all=False)
    assert shim == oracle
    assert "and 5 more..." in shim[1][0][3]  # suggestion contains truncation


# ---------------------------------------------------------------------------
# Differential — impossible constraints
# ---------------------------------------------------------------------------


def _comp(ref: str, w: float = 1.0, h: float = 1.0):
    return (ref, (w, h))


@settings(max_examples=60, deadline=None)
@given(
    st.lists(st.tuples(_REF, _MM, _MM), min_size=0, max_size=8),
    st.lists(
        st.tuples(
            st.text(min_size=1, max_size=4),
            _BOUNDS,
            st.lists(_REF, min_size=0, max_size=3),
        ),
        min_size=0,
        max_size=4,
    ),
    st.lists(st.tuples(_REF, st.text(min_size=1, max_size=4)), min_size=0, max_size=6),
    st.lists(
        st.tuples(
            st.text(min_size=1, max_size=6),
            st.one_of(st.none(), st.text(min_size=1, max_size=4)),
            st.lists(_REF, min_size=0, max_size=5),
        ),
        min_size=0,
        max_size=4,
    ),
    st.lists(st.lists(_REF, min_size=0, max_size=5), min_size=0, max_size=3),
)
def test_impossible_differential_random(comps, zones, assignments, groups, thermals):
    netlist = _netlist([(r, (w, h)) for r, w, h in comps])
    constraints = _constraints(
        zones,
        assignments=dict(assignments),
        groups=groups,
        thermals=thermals,
    )
    oracle, shim = _run_impossible_both(netlist, constraints)
    assert shim == oracle


def test_impossible_differential_hand_built():
    netlist = _netlist([_comp("LARGE", 60.0, 60.0), _comp("SMALL", 5.0, 5.0)])
    # Component too large for its assigned zone (both orientations fail).
    constraints = _constraints(
        [("SMALL_ZONE", (0, 0, 30, 30), [])],
        assignments={"LARGE": "SMALL_ZONE", "SMALL": "SMALL_ZONE"},
    )
    oracle, shim = _run_impossible_both(netlist, constraints)
    assert shim == oracle
    assert any(i[1] == "CONSTRAINT_002" for i in shim[1])
    assert not shim[0]

    # Fit in one orientation only -> no CONSTRAINT_002.
    netlist = _netlist([_comp("WIDE", 25.0, 5.0)])
    constraints = _constraints(
        [("Z", (0, 0, 10, 30), [])], assignments={"WIDE": "Z"}
    )
    oracle, shim = _run_impossible_both(netlist, constraints)
    assert shim == oracle
    assert shim[0] is True

    # EXACT boundary: component size == zone size on the fitting dimension
    # (fits normal-only, not rotated) — the `<=` arm. Anti-vacuity
    # discriminating case for the CONSTRAINT_002 boundary: a `<=`→`<`
    # mutation must be caught.
    netlist = _netlist([_comp("EXACT", 30.0, 5.0)])
    constraints = _constraints(
        [("Z", (0, 0, 30, 5), [])], assignments={"EXACT": "Z"}
    )
    oracle, shim = _run_impossible_both(netlist, constraints)
    assert shim == oracle
    assert shim[0] is True
    assert not any(i[1] == "CONSTRAINT_002" for i in shim[1])

    # Just over the boundary (30.1 vs 30) -> CONSTRAINT_002 fires.
    netlist = _netlist([_comp("BIG", 30.1, 30.0)])
    constraints = _constraints(
        [("Z", (0, 0, 30, 30), [])], assignments={"BIG": "Z"}
    )
    oracle, shim = _run_impossible_both(netlist, constraints)
    assert shim == oracle
    assert any(i[1] == "CONSTRAINT_002" for i in shim[1])

    # Assignment to nonexistent zone -> CONSTRAINT_001.
    netlist = _netlist([_comp("R1")])
    constraints = _constraints([], assignments={"R1": "MISSING"})
    oracle, shim = _run_impossible_both(netlist, constraints)
    assert shim == oracle
    assert any(i[1] == "CONSTRAINT_001" for i in shim[1])
    assert not shim[0]

    # Group referencing missing components -> CONSTRAINT_003 warning.
    netlist = _netlist([_comp("R1")])
    constraints = _constraints(
        [("Z", (0, 0, 50, 50), [])],
        groups=[("g", "Z", ["R1", "M1", "M2"])],
    )
    oracle, shim = _run_impossible_both(netlist, constraints)
    assert shim == oracle
    assert any(i[1] == "CONSTRAINT_003" for i in shim[1])
    assert shim[0] is True  # warning only

    # Group with nonexistent zone -> CONSTRAINT_004.
    constraints = _constraints([], groups=[("g", "GHOST", ["R1"])])
    oracle, shim = _run_impossible_both(netlist, constraints)
    assert shim == oracle
    assert any(i[1] == "CONSTRAINT_004" for i in shim[1])
    assert not shim[0]

    # Thermal missing components -> CONSTRAINT_005 warning.
    constraints = _constraints([], thermals=[["Q1", "Q2"]])
    oracle, shim = _run_impossible_both(netlist, constraints)
    assert shim == oracle
    assert any(i[1] == "CONSTRAINT_005" for i in shim[1])

    # Fully feasible -> CONSTRAINT_006 info, passed=True.
    netlist = _netlist([_comp("R1", 1.0, 1.0)])
    constraints = _constraints([("Z", (0, 0, 50, 50), [])], assignments={"R1": "Z"})
    oracle, shim = _run_impossible_both(netlist, constraints)
    assert shim == oracle
    assert shim[0] is True
    assert any(i[1] == "CONSTRAINT_006" for i in shim[1])

    # Missing[:5] truncation in the group/thermal suggestions.
    netlist = _netlist([_comp("R1")])
    constraints = _constraints(
        [("Z", (0, 0, 50, 50), [])],
        groups=[("g", "Z", [f"M{i}" for i in range(8)])],
    )
    oracle, shim = _run_impossible_both(netlist, constraints)
    assert shim == oracle


# ---------------------------------------------------------------------------
# PBT — five non-vacuous properties (R1c)
# ---------------------------------------------------------------------------


@settings(max_examples=40, deadline=None)
@given(_BOUNDS, _BOUNDS)
def test_prop1_zones_overlap_is_symmetric(a, b):
    """Overlap is symmetric (the AABB predicate is a conjunction of the two
    axes' interval overlaps)."""
    za = Zone(name="A", bounds=a, net_classes=[], components=[])
    zb = Zone(name="B", bounds=b, net_classes=[], components=[])
    assert shim_zones_overlap(za, zb) == shim_zones_overlap(zb, za)


@settings(max_examples=40, deadline=None)
@given(_IN_BOARD_BOUNDS)
def test_prop2_zone_inside_board_is_always_clean(bounds):
    """A zone fully inside the board (with margin headroom) never produces a
    ZONE_003 error."""
    constraints = _constraints([("Z", bounds, [])], board_w=2000.0, board_h=2000.0)
    result = shim_zones_fit(constraints)
    assert not any(i.code == "ZONE_003" for i in result.issues)
    assert result.passed


@settings(max_examples=40, deadline=None)
@given(
    st.lists(_REF, min_size=0, max_size=10),
    st.lists(_REF, min_size=0, max_size=10),
)
def test_prop3_unassigned_is_the_set_difference(netlist_refs, assigned):
    """The unassigned set equals netlist minus assigned minus fixed, exactly
    (kernel returns the sorted difference)."""
    netlist = _netlist([(r, (1.0, 1.0)) for r in netlist_refs])
    constraints = _constraints([("Z", (0, 0, 50, 50), assigned)])
    result = shim_components_have_zones(netlist, constraints, require_all=False)
    expected = sorted(set(netlist_refs) - set(assigned))
    if expected:
        issue = result.issues[0]
        assert issue.components == expected
        assert issue.details["unassigned_count"] == len(expected)
    else:
        assert any(i.code == "ZONE_002" for i in result.issues)


@settings(max_examples=40, deadline=None)
@given(_MM, _MM)
def test_prop4_large_enough_zone_never_reports_too_large(w, h):
    """A component always fits a zone strictly larger than it in both
    dimensions (normal orientation suffices)."""
    netlist = _netlist([("C", (w, h))])
    constraints = _constraints(
        [("Z", (0, 0, 10 * w + 10, 10 * h + 10), [])], assignments={"C": "Z"}
    )
    result = shim_impossible_constraints(netlist, constraints)
    assert not any(i.code == "CONSTRAINT_002" for i in result.issues)
    assert result.passed


@settings(max_examples=40, deadline=None)
@given(st.lists(_REF, min_size=0, max_size=8))
def test_prop5_warning_severity_tracks_require_all(refs):
    """The same unassigned set flips severity/`passed` exactly with
    require_all."""
    netlist = _netlist([(r, (1.0, 1.0)) for r in refs])
    constraints = _constraints([])
    warn = shim_components_have_zones(netlist, constraints, require_all=False)
    err = shim_components_have_zones(netlist, constraints, require_all=True)
    if refs:
        assert warn.issues[0].severity is PreflightSeverity.WARNING
        assert warn.passed is True
        assert err.issues[0].severity is PreflightSeverity.ERROR
        assert err.passed is False
    else:
        assert warn.passed is True and err.passed is True


# ---------------------------------------------------------------------------
# Metamorphic relations (R1d)
# ---------------------------------------------------------------------------


def test_mr1_scaling_board_with_zone_preserves_clean_status():
    """Scaling a clean zone/board pair by a constant factor preserves
    'no ZONE_003' (all comparisons are order-preserving under positive
    scaling)."""
    base = _constraints([("A", (10, 10, 40, 40), []), ("B", (50, 50, 90, 90), [])])
    assert shim_zones_fit(base).passed
    scaled = _constraints(
        [("A", (20, 20, 80, 80), []), ("B", (100, 100, 180, 180), [])],
        board_w=200.0,
        board_h=200.0,
    )
    assert shim_zones_fit(scaled).passed


def test_mr2_adding_a_fixed_component_cannot_create_unassigned():
    """Growing the fixed set can only shrink or hold the unassigned set."""
    netlist = _netlist([("R1", (1.0, 1.0)), ("R2", (1.0, 1.0)), ("R3", (1.0, 1.0))])
    base = _constraints([], fixed=[])
    base_result = shim_components_have_zones(netlist, base, require_all=True)
    fixed_result = shim_components_have_zones(
        netlist, _constraints([], fixed=["R1", "R2"]), require_all=True
    )
    base_unassigned = set(base_result.issues[0].components) if base_result.issues else set()
    fixed_unassigned = (
        set(fixed_result.issues[0].components) if fixed_result.issues else set()
    )
    assert fixed_unassigned <= base_unassigned


def test_mr3_permuting_zone_list_order_preserves_the_finding_SET():
    """ZONE_004 overlap findings are order-insensitive as a set (the oracle
    enumerates ordered pairs; the finding set is invariant under input
    permutation)."""
    def findings_for(order):
        constraints = _constraints(order, board_w=100.0, board_h=100.0)
        result = shim_zones_fit(constraints)
        return frozenset((i.details.get("zones") and tuple(sorted(i.details["zones"]))) for i in result.issues if i.code == "ZONE_004")

    zones = [("A", (0, 0, 60, 60), []), ("B", (40, 40, 100, 100), []), ("C", (50, 50, 80, 80), [])]
    forward = findings_for(zones)
    reversed_order = findings_for(list(reversed(zones)))
    assert forward == reversed_order
    assert len(forward) == 3  # AB, AC, BC all overlap
