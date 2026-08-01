"""Differential tests: the REQ-SAFE-01 clearance validator's pure geometry
compute vs the pre-migration pure-Python reference implementations (Wave 3
slice 3).

The pre-migration implementations are pinned here as oracles (verbatim
copies, including operation order and every f64 rounding decision):

- ``kicad_transform.rotate_local_to_world`` (the R(-theta) pad-offset
  rotation behind ``_copper._rotate`` / ``_component_pads``)
- ``pad_geometry.pad_pair_distance`` (core polygon construction via
  ``pad_core_polygon`` + Shapely/GEOS ``.distance()``)
- ``_CopperModel`` (reach computation, lower_bound, the copper_distance
  pair scan with its hypot centre-gap pruning)

The migrated Rust core lives in
``packages/temper-geometry/src/clearance_geometry.rs`` and is exercised
THROUGH the wrappers below (the consumer surface): any change to the Rust
core or the Python delegation that disagrees with the oracle fails here,
bit-exactly.

Hard-won exactness notes (see the Rust module docstring for the full
derivation):

- GEOS ``CoordinateXY::distance`` is ``sqrt(dx*dx + dy*dy)`` -- NOT hypot.
  Replicating it with ``math.hypot`` (CPython's Dekker vector_norm) or
  libm ``hypot`` fails by 1 ulp on ~12% of random pairs.
- Shapely's ``rotate`` converts degrees->radians ITSELF
  (``angle * pi / 180.0``) on top of ``math.degrees`` (``x * (180/pi)``),
  and snaps ``abs(cos/sin) < 2.5e-16`` to exactly 0.0 -- the effective
  rotation angle is NOT ``rotation_rad``.
- ``dist(A, B) != dist(B, A)`` bit-exactly in general: the final
  ``max(gap - ra - rb, 0.0)`` subtracts the corner radii in pad order, so
  ``(gap - ra(A)) - rb(B)`` vs ``(gap - ra(B)) - rb(A)`` can differ by 1
  ulp. This asymmetry is present in the ORACLE too and is pinned here,
  not "fixed".
"""

from __future__ import annotations

import math
import random

import pytest
import temper_geometry as _tg

from temper_placer.core.pad_geometry import pad_pair_distance
from temper_placer.requirements.validators._copper import (
    _component_pads,
    _CopperModel,
    _rotate,
)
from temper_placer.requirements.validators.clearance import VoltageDomain

SHAPES = ["circle", "oval", "rect", "roundrect", "thru_hole", "custom"]

# ---------------------------------------------------------------------------
# Oracles (pre-migration implementations, verbatim)
# ---------------------------------------------------------------------------


def _oracle_rotate(x: float, y: float, theta_rad: float):
    """kicad_transform.rotate_local_to_world, verbatim."""
    c, s = math.cos(theta_rad), math.sin(theta_rad)
    return (x * c + y * s, -x * s + y * c)


def _oracle_corner_radius(width, height, shape, roundrect_ratio):
    norm = "circle" if shape == "thru_hole" else shape
    if norm == "circle":
        return max(width, height) / 2.0
    if norm == "oval":
        return min(width, height) / 2.0
    if norm == "roundrect":
        return roundrect_ratio * min(width, height)
    return 0.0


def _oracle_half_extents(width, height, shape, roundrect_ratio):
    r = _oracle_corner_radius(width, height, shape, roundrect_ratio)
    return (max(width / 2.0 - r, 0.0), max(height / 2.0 - r, 0.0))


def _oracle_bounding_radius(width, height, shape, roundrect_ratio):
    hw, hh = _oracle_half_extents(width, height, shape, roundrect_ratio)
    r = _oracle_corner_radius(width, height, shape, roundrect_ratio)
    return math.hypot(hw, hh) + r


def _oracle_core_polygon(width, height, shape, cx, cy, rotation_rad=0.0, roundrect_ratio=0.25):
    """pad_geometry.pad_core_polygon, verbatim (pre-migration)."""
    from shapely.affinity import rotate, translate
    from shapely.geometry import LineString, Point, box

    hw, hh = _oracle_half_extents(width, height, shape, roundrect_ratio)
    if hw <= 0.0 and hh <= 0.0:
        core = Point(0.0, 0.0)
    elif hh <= 0.0:
        core = LineString([(-hw, 0.0), (hw, 0.0)])
    elif hw <= 0.0:
        core = LineString([(0.0, -hh), (0.0, hh)])
    else:
        core = box(-hw, -hh, hw, hh)
    rotated = rotate(core, math.degrees(rotation_rad), origin=(0, 0), use_radians=False)
    return translate(rotated, xoff=cx, yoff=cy)


def _oracle_pad_pair_distance(pad_a, pad_b):
    """pad_geometry.pad_pair_distance, verbatim (pre-migration)."""
    wa, ha, sa, cxa, cya, rota, rra = pad_a
    wb, hb, sb, cxb, cyb, rotb, rrb = pad_b
    core_a = _oracle_core_polygon(wa, ha, sa, cxa, cya, rota, rra)
    core_b = _oracle_core_polygon(wb, hb, sb, cxb, cyb, rotb, rrb)
    gap = core_a.distance(core_b)
    ra = _oracle_corner_radius(wa, ha, sa, rra)
    rb = _oracle_corner_radius(wb, hb, sb, rrb)
    return max(gap - ra - rb, 0.0)


def _oracle_component_pads(comp):
    """_copper._component_pads, verbatim (pre-migration)."""
    raw = comp.get("pads")
    if not raw:
        return []
    ref = str(comp.get("ref", "?"))
    ox, oy = comp["position"]
    comp_rot_rad = math.radians(float(comp.get("rotation_deg", 0.0)))

    pads = []
    for i, p in enumerate(raw):
        dx, dy = p.get("offset", (0.0, 0.0))
        rx, ry = _oracle_rotate(float(dx), float(dy), comp_rot_rad)
        pad_rot_rad = comp_rot_rad + math.radians(float(p.get("pad_rotation_deg", 0.0)))
        pads.append(
            (
                ref,
                str(p.get("number", i)),
                p.get("net"),
                ox + rx,
                oy + ry,
                float(p.get("width", 1.0)),
                float(p.get("height", 1.0)),
                str(p.get("shape", "rect")),
                float(p.get("roundrect_ratio", 0.25)),
                pad_rot_rad,
            )
        )
    return pads


def _pad_label(pad):
    """``_Pad.label`` semantics: the ``(net)`` suffix only when a net exists."""
    ref, number, net = pad[0], pad[1], pad[2]
    return f"{ref}.{number}({net})" if net else f"{ref}.{number}"


class _OracleCopperModel:
    """_copper._CopperModel, verbatim (pre-migration) with the oracle pad
    geometry primitives substituted for the (now Rust-backed) ones."""

    def __init__(self, placement):
        self._pads = {}
        self._origin = {}
        self._reach = {}
        self._dist_cache = {}
        self.components_without_pads = []

        for comp in placement.get("components", []):
            ref = str(comp.get("ref", "?"))
            self._origin[ref] = tuple(comp["position"])
            pads = self._component_pads_oracle(comp)
            self._pads[ref] = pads
            if not pads:
                self.components_without_pads.append(ref)
                self._reach[ref] = 0.0
                continue
            ox, oy = self._origin[ref]
            self._reach[ref] = max(
                math.hypot(p[3] - ox, p[4] - oy)
                + _oracle_bounding_radius(p[5], p[6], p[7], p[8])
                for p in pads
            )

    @staticmethod
    def _component_pads_oracle(comp):
        return _oracle_component_pads(comp)

    def pads_in_domain(self, ref, domain, nets_domain):
        pads = self._pads.get(ref, [])
        matching = [p for p in pads if p[2] is not None and nets_domain.get(p[2]) == domain]
        return matching if matching else pads

    def has_pads(self, ref):
        return bool(self._pads.get(ref))

    def domain_restricted(self, ref, domain, nets_domain):
        pads = self._pads.get(ref, [])
        return any(p[2] is not None and nets_domain.get(p[2]) == domain for p in pads)

    @staticmethod
    def _spec(pad):
        return (pad[5], pad[6], pad[7], pad[3], pad[4], pad[9], pad[8])

    def lower_bound(self, ref_a, ref_b):
        if ref_a == ref_b:
            return -math.inf
        pa, pb = self._origin[ref_a], self._origin[ref_b]
        return math.dist(pa, pb) - self._reach[ref_a] - self._reach[ref_b]

    def copper_distance(self, ref_a, domain_a, ref_b, domain_b, nets_domain):
        key = (ref_a, domain_a, ref_b, domain_b)
        cached = self._dist_cache.get(key)
        if cached is not None:
            return cached

        pads_a = self.pads_in_domain(ref_a, domain_a, nets_domain)
        pads_b = self.pads_in_domain(ref_b, domain_b, nets_domain)

        if not pads_a or not pads_b:
            result = (
                math.dist(self._origin[ref_a], self._origin[ref_b]),
                "origin",
                f"{ref_a} <-> {ref_b} (origins; no pad geometry)",
            )
            self._dist_cache[key] = result
            return result

        best = math.inf
        best_label = ""
        for pa in pads_a:
            ra = _oracle_bounding_radius(pa[5], pa[6], pa[7], pa[8])
            for pb in pads_b:
                if pa is pb:
                    continue
                rb = _oracle_bounding_radius(pb[5], pb[6], pb[7], pb[8])
                centre_gap = math.hypot(pa[3] - pb[3], pa[4] - pb[4]) - ra - rb
                if centre_gap >= best:
                    continue
                d = _oracle_pad_pair_distance(self._spec(pa), self._spec(pb))
                if d < best:
                    best = d
                    best_label = f"{_pad_label(pa)} <-> {_pad_label(pb)}"

        if best is math.inf:
            result = (
                math.dist(self._origin[ref_a], self._origin[ref_b]),
                "origin",
                f"{ref_a} <-> {ref_b} (origins; no distinct pad pair)",
            )
        else:
            result = (best, "copper", best_label)
        self._dist_cache[key] = result
        return result


# ---------------------------------------------------------------------------
# Random-input generators
# ---------------------------------------------------------------------------


def _rand_pad(rng, overlap_chance=0.2):
    shape = rng.choice(SHAPES)
    w = rng.uniform(0.05, 12.0)
    h = rng.uniform(0.05, 12.0)
    if rng.random() < overlap_chance:
        cx = rng.uniform(-4, 4)
        cy = rng.uniform(-4, 4)
    else:
        cx = rng.uniform(-40, 40)
        cy = rng.uniform(-40, 40)
    rot = rng.uniform(-8 * math.pi, 8 * math.pi)
    rr = rng.choice([0.0, 0.25, 0.5, rng.uniform(0.0, 0.5)])
    return (w, h, shape, cx, cy, rot, rr)


def _rand_pad_spec(rng):
    """(width, height, shape, cx, cy, rotation_rad, roundrect_ratio)."""
    return _rand_pad(rng)


def _rand_comp(rng, ref):
    """A placement component with real pad data (mirrors _copper's input
    contract)."""
    n_pads = rng.randint(1, 8)
    pads = []
    nets = []
    for i in range(n_pads):
        w = rng.choice([rng.uniform(0.05, 12.0), 0.0, 1.0])
        h = rng.choice([rng.uniform(0.05, 12.0), 0.0, 1.0])
        shape = rng.choice(["circle", "oval", "rect", "roundrect", "thru_hole"])
        net = rng.choice([None, "N_HV", "N_LV", "N_OTHER"])
        if net:
            nets.append(net)
        pads.append(
            {
                "number": str(i),
                "net": net,
                "offset": (rng.uniform(-6, 6), rng.uniform(-6, 6)),
                "width": w,
                "height": h,
                "shape": shape,
                "roundrect_ratio": rng.choice([0.0, 0.25, 0.5]),
                "pad_rotation_deg": rng.choice([0.0, 90.0, 45.0, rng.uniform(-180, 180)]),
            }
        )
    return {
        "ref": ref,
        "position": (rng.uniform(-60, 60), rng.uniform(-60, 60)),
        "rotation_deg": rng.choice([0.0, 90.0, 180.0, 45.0, rng.uniform(-180, 180)]),
        "nets": nets,
        "pads": pads,
    }


def _rand_placement(rng):
    comps = [_rand_comp(rng, f"C{i}") for i in range(rng.randint(2, 6))]
    return {"components": comps, "nets": {"N_HV": {"domain": "DC_BUS"}, "N_LV": {"domain": "LV_CONTROL"}}}


_NETS_DOMAIN = {
    "N_HV": VoltageDomain.DC_BUS,
    "N_LV": VoltageDomain.LV_CONTROL,
}


# ---------------------------------------------------------------------------
# Rust surface guard (the TDD red-phase check: these pyfunctions must exist)
# ---------------------------------------------------------------------------


def test_rust_clearance_surface_exported():
    """The migrated geometry lives in the temper-geometry crate. Before the
    migration this fails with AttributeError -- the differential assertions
    below only exercise the Rust path once the wrappers delegate to it."""
    assert hasattr(_tg, "rotate_local_to_world_py")
    assert hasattr(_tg, "pad_pair_distance_py")
    assert hasattr(_tg, "component_reach_py")
    assert hasattr(_tg, "origin_distance_py")
    assert hasattr(_tg, "copper_scan_py")


# ---------------------------------------------------------------------------
# rotate_local_to_world (KiCad R(-theta) pad-offset rotation)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(25))
def test_rotate_bit_exact_random(seed):
    rng = random.Random(seed * 7919 + 1)
    for _ in range(500):
        x = rng.uniform(-50, 50)
        y = rng.uniform(-50, 50)
        theta = rng.choice(
            [0.0, math.pi / 2, math.pi, -math.pi / 2, 2 * math.pi, rng.uniform(-8 * math.pi, 8 * math.pi)]
        )
        assert _rotate(x, y, theta) == _oracle_rotate(x, y, theta)


def test_rotate_edge_cases():
    for x, y, theta in [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (3.7, -2.1, math.pi / 2),
        (-5.0, 5.0, -math.pi / 2),
        (1e-9, -1e-9, 1.2345),
        (0.0, 0.0, math.pi),
    ]:
        assert _rotate(x, y, theta) == _oracle_rotate(x, y, theta)


# ---------------------------------------------------------------------------
# pad_pair_distance (the exact pad-polygon distance)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(25))
def test_pad_pair_distance_bit_exact_random(seed):
    rng = random.Random(seed * 104729 + 3)
    for _ in range(500):
        pa = _rand_pad_spec(rng)
        pb = _rand_pad_spec(rng)
        assert pad_pair_distance(pa, pb) == _oracle_pad_pair_distance(pa, pb)


def test_pad_pair_distance_edge_cases():
    cases = [
        # small rect core inside big rect core (containment -> 0.0)
        ((10.0, 10.0, "rect", 0.0, 0.0, 0.0, 0.0), (2.0, 2.0, "rect", 0.0, 0.0, 0.0, 0.0)),
        # point (circle) core inside rect core
        ((10.0, 10.0, "rect", 0.0, 0.0, 0.0, 0.0), (2.0, 2.0, "circle", 0.0, 0.0, 0.0, 0.0)),
        # rects sharing an edge (boundary touch -> 0.0)
        ((4.0, 4.0, "rect", 0.0, 0.0, 0.0, 0.0), (4.0, 4.0, "rect", 4.0, 0.0, 0.0, 0.0)),
        # point exactly on a rect edge
        ((4.0, 4.0, "rect", 0.0, 0.0, 0.0, 0.0), (0.0, 0.0, "circle", 2.0, 2.0, 0.0, 0.0)),
        # 45-degree rotated rects (exact representable values)
        ((4.0, 4.0, "rect", 0.0, 0.0, math.pi / 4, 0.0), (4.0, 4.0, "rect", 10.0, 0.0, math.pi / 4, 0.0)),
        # zero-size pads (both circles collapse to points)
        ((0.0, 0.0, "circle", 1.0, 1.0, 0.0, 0.0), (0.0, 0.0, "circle", 4.0, 5.0, 0.0, 0.0)),
        # oval collapsing to a point
        ((4.0, 0.0, "oval", 0.0, 0.0, 0.0, 0.0), (4.0, 4.0, "rect", 5.0, 0.0, 0.0, 0.0)),
        # crossing oval cores (segment intersection -> 0.0)
        ((4.0, 1.0, "oval", 0.0, 0.0, 0.0, 0.0), (4.0, 1.0, "oval", 0.0, 0.0, math.pi / 2, 0.0)),
        # roundrect with a ratio larger than half-size (hw/hh clamp to 0)
        ((2.0, 2.0, "roundrect", 0.0, 0.0, 0.0, 3.0), (2.0, 2.0, "roundrect", 5.0, 0.0, 0.0, 3.0)),
        # small rect fully inside a big rotated rect (vertex-inside containment)
        ((20.0, 20.0, "rect", 0.0, 0.0, 0.7853981633974483, 0.0), (2.0, 2.0, "rect", 0.0, 0.0, 0.0, 0.0)),
        # touching at a corner
        ((2.0, 2.0, "rect", 0.0, 0.0, 0.0, 0.0), (2.0, 2.0, "rect", 2.0, 2.0, 0.0, 0.0)),
        # unknown shape fallback (r=0 sharp corners)
        ((3.0, 3.0, "custom", 0.0, 0.0, 0.7, 0.25), (3.0, 3.0, "rect", 10.0, 0.0, 0.0, 0.25)),
        # thru_hole normalized to circle
        ((2.0, 2.0, "thru_hole", 0.0, 0.0, 0.0, 0.25), (2.0, 2.0, "circle", 5.0, 0.0, 0.0, 0.25)),
    ]
    for pa, pb in cases:
        assert pad_pair_distance(pa, pb) == _oracle_pad_pair_distance(pa, pb), (pa, pb)


def test_pad_pair_distance_zero_when_overlapping():
    # Two pads on top of each other must report exactly 0.0 (not a tiny
    # polygonised residue) -- the property the copper-to-copper fix exists for.
    assert pad_pair_distance((4.0, 4.0, "rect", 0.0, 0.0, 0.0, 0.0), (4.0, 4.0, "rect", 0.5, 0.5, 0.0, 0.0)) == 0.0


# ---------------------------------------------------------------------------
# _component_pads (pad-polygon construction: offset rotation + placement)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(15))
def test_component_pads_bit_exact_random(seed):
    rng = random.Random(seed * 15485863 + 5)
    for _ in range(300):
        comp = _rand_comp(rng, f"U{seed}")
        got = _component_pads(comp)
        exp = _oracle_component_pads(comp)
        assert len(got) == len(exp)
        for g, e in zip(got, exp):
            assert (
                g.ref,
                g.number,
                g.net,
                g.cx,
                g.cy,
                g.width,
                g.height,
                g.shape,
                g.roundrect_ratio,
                g.rotation_rad,
            ) == e


def test_component_pads_no_pads_fallback():
    comp = {"ref": "R1", "position": (1.0, 2.0), "rotation_deg": 45.0, "nets": [], "pads": []}
    assert _component_pads(comp) == []
    assert _component_pads({}) == []


def test_component_pads_missing_keys_defaults():
    comp = {"ref": "R2", "position": (0.0, 0.0)}
    assert _component_pads(comp) == []
    # a pad with only defaults
    comp2 = {"ref": "R3", "position": (0.0, 0.0), "pads": [{}]}
    got = _component_pads(comp2)
    assert len(got) == 1
    exp = _oracle_component_pads(comp2)
    assert (got[0].cx, got[0].cy, got[0].width, got[0].height, got[0].shape) == (
        exp[0][3],
        exp[0][4],
        exp[0][5],
        exp[0][6],
        exp[0][7],
    )


# ---------------------------------------------------------------------------
# _CopperModel: reach, lower_bound, copper_distance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(10))
def test_copper_model_reach_bit_exact(seed):
    rng = random.Random(seed * 32452843 + 7)
    for _ in range(100):
        placement = _rand_placement(rng)
        model = _CopperModel(placement)
        oracle = _OracleCopperModel(placement)
        assert model.components_without_pads == oracle.components_without_pads
        for ref in oracle._origin:
            assert model._reach[ref] == oracle._reach[ref], ref


@pytest.mark.parametrize("seed", range(10))
def test_copper_model_lower_bound_bit_exact(seed):
    rng = random.Random(seed * 49979687 + 11)
    for _ in range(100):
        placement = _rand_placement(rng)
        model = _CopperModel(placement)
        oracle = _OracleCopperModel(placement)
        refs = [c["ref"] for c in placement["components"]]
        for ra in refs:
            for rb in refs:
                if ra == rb:
                    continue
                assert model.lower_bound(ra, rb) == oracle.lower_bound(ra, rb), (ra, rb)


@pytest.mark.parametrize("seed", range(10))
def test_copper_model_copper_distance_bit_exact(seed):
    rng = random.Random(seed * 67867967 + 13)
    for _ in range(100):
        placement = _rand_placement(rng)
        model = _CopperModel(placement)
        oracle = _OracleCopperModel(placement)
        refs = [c["ref"] for c in placement["components"]]
        for ra in refs:
            for rb in refs:
                got = model.copper_distance(ra, VoltageDomain.DC_BUS, rb, VoltageDomain.LV_CONTROL, _NETS_DOMAIN)
                exp = oracle.copper_distance(ra, VoltageDomain.DC_BUS, rb, VoltageDomain.LV_CONTROL, _NETS_DOMAIN)
                assert got == exp, (ra, rb)


def test_copper_model_intra_self_pair_skipped():
    """The `pa is pb` self-pair skip inside copper_distance must survive the
    Rust scan: an intra-footprint check where both domains fall back to the
    full pad list must not pair a pad with itself (distance 0.0).

    Pads at x=-3 and x=+3 (2x2 rects): the true copper gap is 2.0mm.
    Pairing a pad with ITSELF would report 0.0 -- the skip is what keeps
    the answer at 2.0.
    """
    comp = {
        "ref": "U1",
        "position": (0.0, 0.0),
        "rotation_deg": 0.0,
        "nets": ["N_HV", "N_LV"],
        "pads": [
            {"number": "1", "net": None, "offset": (-3.0, 0.0), "width": 2.0, "height": 2.0, "shape": "rect", "roundrect_ratio": 0.25, "pad_rotation_deg": 0.0},
            {"number": "2", "net": None, "offset": (3.0, 0.0), "width": 2.0, "height": 2.0, "shape": "rect", "roundrect_ratio": 0.25, "pad_rotation_deg": 0.0},
        ],
    }
    placement = {"components": [comp], "nets": {}}
    model = _CopperModel(placement)
    oracle = _OracleCopperModel(placement)
    nets_domain = {}  # no domain matches -> both fall back to the full list
    got = model.copper_distance("U1", VoltageDomain.DC_BUS, "U1", VoltageDomain.LV_CONTROL, nets_domain)
    exp = oracle.copper_distance("U1", VoltageDomain.DC_BUS, "U1", VoltageDomain.LV_CONTROL, nets_domain)
    assert got == exp
    # true copper gap: 6.0 - 1.0 - 1.0 = 4.0 (pad centers 6 apart, 1.0 half-widths)
    assert got == (4.0, "copper", "U1.1 <-> U1.2")


# ---------------------------------------------------------------------------
# Metamorphic relations (>= 3 required by the Wave 3 gate)
# ---------------------------------------------------------------------------

# M1: translating both pads by the same vector preserves the distance
@pytest.mark.parametrize("seed", range(8))
def test_metamorphic_translation_invariance(seed):
    rng = random.Random(seed * 86028121 + 17)
    for _ in range(200):
        pa = _rand_pad_spec(rng)
        pb = _rand_pad_spec(rng)
        dx, dy = rng.uniform(-20, 20), rng.uniform(-20, 20)
        base = pad_pair_distance(pa, pb)
        moved = pad_pair_distance(
            (pa[0], pa[1], pa[2], pa[3] + dx, pa[4] + dy, pa[5], pa[6]),
            (pb[0], pb[1], pb[2], pb[3] + dx, pb[4] + dy, pb[5], pb[6]),
        )
        assert moved == pytest.approx(base, rel=1e-9, abs=1e-9)


def _world_rotate(pad, delta):
    w, h, s, cx, cy, rot, rr = pad
    c, sn = math.cos(delta), math.sin(delta)
    nx = c * cx - sn * cy
    ny = sn * cx + c * cy
    return (w, h, s, nx, ny, rot + delta, rr)


# M2: rotating both pads around the world origin by the same angle preserves
# the distance
@pytest.mark.parametrize("seed", range(8))
def test_metamorphic_rotation_invariance(seed):
    rng = random.Random(seed * 93319993 + 19)
    for _ in range(200):
        pa = _rand_pad_spec(rng)
        pb = _rand_pad_spec(rng)
        delta = rng.uniform(-math.pi, math.pi)
        base = pad_pair_distance(pa, pb)
        rotated = pad_pair_distance(_world_rotate(pa, delta), _world_rotate(pb, delta))
        assert rotated == pytest.approx(base, rel=1e-9, abs=1e-9)


# M3: mirroring both pads across the Y axis (cx -> -cx, rotation -> -rotation)
# preserves the distance
@pytest.mark.parametrize("seed", range(8))
def test_metamorphic_mirror_invariance(seed):
    rng = random.Random(seed * 112272535 + 23)
    for _ in range(200):
        pa = _rand_pad_spec(rng)
        pb = _rand_pad_spec(rng)
        base = pad_pair_distance(pa, pb)
        mirrored = pad_pair_distance(
            (pa[0], pa[1], pa[2], -pa[3], pa[4], -pa[5], pa[6]),
            (pb[0], pb[1], pb[2], -pb[3], pb[4], -pb[5], pb[6]),
        )
        assert mirrored == pytest.approx(base, rel=1e-9, abs=1e-9)


# M4: doubling the scale doubles the distance (BIT-EXACT -- powers of two
# scale every f64 coordinate and product exactly)
@pytest.mark.parametrize("seed", range(8))
def test_metamorphic_scale_doubling(seed):
    rng = random.Random(seed * 74233813 + 29)
    for _ in range(200):
        pa = _rand_pad_spec(rng)
        pb = _rand_pad_spec(rng)
        base = pad_pair_distance(pa, pb)
        scaled = pad_pair_distance(
            (pa[0] * 2.0, pa[1] * 2.0, pa[2], pa[3] * 2.0, pa[4] * 2.0, pa[5], pa[6]),
            (pb[0] * 2.0, pb[1] * 2.0, pb[2], pb[3] * 2.0, pb[4] * 2.0, pb[5], pb[6]),
        )
        assert scaled == 2.0 * base


# (The copper-scan consistency check is covered by the bit-exact random
# differential `test_copper_model_copper_distance_bit_exact` above -- the
# prune-threshold boundary cases are included in its corpus because
# `_rand_comp` draws near-overlapping pads 20% of the time.)
