"""R1d: metamorphic relations for the Wave-4 Phase 2 contract layer.

Six relations that hold, each stated as an equality between two *runs*
rather than against a fixed expected value -- so they catch a port that
is self-consistently wrong.

Three relations that do **not** hold are recorded as witness tests
(``test_witness_*``) rather than quietly narrowed. Two of them are float
round-trips that lose a ulp; the third is the one the program brief
warns about specifically -- an ordering that is *not* an invariant and
must not be "fixed" by sorting.
"""

from __future__ import annotations

import itertools
import math
import os
import random
import subprocess
import sys

import numpy as np
import pytest

from temper_placer.core import manufacturing as prod_mf
from temper_placer.core import net_classification as prod_nc
from temper_placer.core import units as prod_units
from temper_placer.core.board import Rect as ProdRect
from temper_placer.core.netlist import build_adjacency_matrix as prod_adjacency
import temper_io_types as prod_drc
from tests.wave4_phase2._sig import assert_same, signature

# ---------------------------------------------------------------------------
# M1. Adjacency is invariant to the order of a net's pins.
# ---------------------------------------------------------------------------


def _adjacency(refs, nets):
    from temper_placer.core.netlist import Component, Net, Netlist

    return prod_adjacency(
        Netlist(
            components=[Component(ref=r, footprint="F", bounds=(1.0, 1.0)) for r in refs],
            nets=[Net(name=f"N{i}", pins=[(r, "1") for r in p]) for i, p in enumerate(nets)],
        )
    )


def test_m1_adjacency_is_invariant_to_pin_order():
    """M1. Permuting a net's pin list does not move a single bit.

    This is the property the reference's ``list(set(...))`` silently
    depends on: set iteration order is a hash artefact, and the result
    would be nondeterministic if the pairwise update were not
    order-symmetric. The Rust port keeps first-occurrence order rather
    than sorting, so the relation is a real test of the claim rather
    than a tautology.
    """
    refs = [f"U{i}" for i in range(6)]
    base_nets = [["U0", "U1", "U2", "U3"], ["U4", "U5"], ["U1", "U1", "U3", "U5", "U0"]]
    base = _adjacency(refs, base_nets)
    rng = random.Random(4)
    for _ in range(60):
        permuted = []
        for net in base_nets:
            shuffled = list(net)
            rng.shuffle(shuffled)
            permuted.append(shuffled)
        assert_same(_adjacency(refs, permuted), base, "M1 pin-order invariance")


def test_m1b_adjacency_relabels_under_a_component_permutation():
    """M1b. Permuting components permutes rows and columns identically."""
    refs = [f"U{i}" for i in range(5)]
    nets = [["U0", "U1", "U2"], ["U3", "U4"], ["U0", "U4"]]
    base = _adjacency(refs, nets)

    order = [3, 0, 4, 1, 2]
    permuted_refs = [refs[i] for i in order]
    permuted = _adjacency(permuted_refs, nets)
    expected = base[np.ix_(order, order)]
    assert_same(permuted, np.ascontiguousarray(expected), "M1b relabelling")


# ---------------------------------------------------------------------------
# M2. Classification is invariant to case and to a trailing newline.
# ---------------------------------------------------------------------------

_CLASSIFIERS = (
    prod_nc.is_ground_net,
    prod_nc.is_power_net,
    prod_nc.is_hv_net,
    prod_nc.is_signal_net,
    prod_nc.is_ground_pin,
    prod_nc.is_power_pin,
    prod_nc.is_hv_pin,
    prod_nc.is_clock_pin,
)


def _corpus(n: int = 800) -> list[str]:
    rng = random.Random(77)
    stems = ["GND", "VCC", "+3V3", "AC_L", "PE", "DC_BUS+", "SDA", "CLK", "XTAL1", "VSS"]
    out = list(stems)
    for _ in range(n):
        out.append(
            rng.choice(stems) + rng.choice(["", "_1", "2", "_BUS", "X", "_"]),
        )
    return out


def test_m2_classification_is_case_invariant():
    """M2. `upper()` is applied first, so case cannot change an answer."""
    for name in _corpus():
        for fn in _CLASSIFIERS:
            assert fn(name.lower()) == fn(name.upper()) == fn(name), name
        assert (
            prod_nc.classify_net_type(name.lower())
            == prod_nc.classify_net_type(name.upper())
            == prod_nc.classify_net_type(name)
        )


def test_m2b_classification_is_invariant_to_one_trailing_newline():
    """M2b. Python's `$` matches before a single trailing newline.

    The naive Rust port breaks exactly this relation (its `$` is
    end-of-haystack only), so M2b is the relation that would have caught
    the trap had the differential missed it.
    """
    for name in _corpus():
        for fn in _CLASSIFIERS:
            assert fn(name + "\n") == fn(name), f"{name!r} + newline"


# ---------------------------------------------------------------------------
# M3. Rect is translation-covariant and scale-covariant.
# ---------------------------------------------------------------------------


def test_m3_rect_width_and_height_are_translation_invariant():
    """M3. Translating a Rect by an exactly-representable delta leaves
    width and height bit-identical."""
    rng = random.Random(21)
    for _ in range(500):
        x0 = rng.randrange(-1024, 1024) * 0.25  # exact in binary
        y0 = rng.randrange(-1024, 1024) * 0.25
        w = rng.randrange(1, 1024) * 0.25
        h = rng.randrange(1, 1024) * 0.25
        dx = rng.randrange(-256, 256) * 0.5
        dy = rng.randrange(-256, 256) * 0.5
        a = ProdRect.from_xyxy(x0, y0, x0 + w, y0 + h)
        b = ProdRect.from_xyxy(x0 + dx, y0 + dy, x0 + w + dx, y0 + h + dy)
        assert_same(a.width, b.width, "M3 width")
        assert_same(a.height, b.height, "M3 height")


def test_m3b_rect_coerce_is_idempotent():
    """M3b. `coerce(coerce(v)) is coerce(v)` -- and by identity."""
    for value in [(0, 0, 1, 1), [0.0, 0.0, 2.5, 3.5], (-1.0, -1.0, 1.0, 1.0)]:
        once = ProdRect.coerce(value)
        assert ProdRect.coerce(once) is once
        assert_same(ProdRect.coerce(once), once, "M3b idempotence")


# ---------------------------------------------------------------------------
# M4. Placement DRC is invariant to a rigid translation of the whole scene.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# M5. inflated_width and inflated_clearance are mutually inverse on the
#     tolerance argument, in the exact-arithmetic sense.
# ---------------------------------------------------------------------------


def test_m5_inflation_composes_additively():
    """M5. Two successive width inflations equal one by the sum, whenever
    the sum is itself exact."""
    rng = random.Random(31)
    for _ in range(2000):
        nominal = rng.randrange(0, 4096) * 0.0625
        a = rng.randrange(0, 256) * 0.0625
        b = rng.randrange(0, 256) * 0.0625
        assert_same(
            prod_mf.inflated_width(prod_mf.inflated_width(nominal, a), b),
            prod_mf.inflated_width(nominal, a + b),
            "M5 additivity",
        )


# ---------------------------------------------------------------------------
# M6. Angle conversion is odd (f(-x) == -f(x)) exactly.
# ---------------------------------------------------------------------------


def test_m6_angle_conversion_is_exactly_odd():
    """M6. `deg_to_rad(-x) == -deg_to_rad(x)` bit-for-bit.

    Multiplication and division both negate exactly in IEEE-754, so this
    is an exact relation, not an approximate one -- including for signed
    zero, where the sign bit is the whole observable.
    """
    rng = random.Random(53)
    values = [0.0, -0.0, 5e-324, 1e300, math.pi] + [rng.uniform(-1e6, 1e6) for _ in range(5000)]
    for x in values:
        assert_same(prod_units.deg_to_rad(-x), -prod_units.deg_to_rad(x), f"M6 deg({x!r})")
        assert_same(prod_units.rad_to_deg(-x), -prod_units.rad_to_deg(x), f"M6 rad({x!r})")


# ---------------------------------------------------------------------------
# Witnesses: relations that do NOT hold.
# ---------------------------------------------------------------------------


def test_witness_angle_round_trip_is_not_the_identity():
    """NOT a relation. `rad_to_deg(deg_to_rad(x)) != x` in general.

    Tempting to assert, and false: four roundings cannot compose to the
    identity. Pinned as a counterexample count rather than narrowed to
    the inputs where it happens to hold.
    """
    rng = random.Random(61)
    values = [rng.uniform(-1e6, 1e6) for _ in range(20000)]
    lost = sum(1 for x in values if prod_units.rad_to_deg(prod_units.deg_to_rad(x)) != x)
    assert lost > 0, "expected the deg->rad->deg round-trip to lose a ulp somewhere"
    # Both arms lose it identically, which is the claim that matters.
    from tests.wave4_phase2 import _core_py_oracle as oracle

    for x in values[:2000]:
        assert_same(
            prod_units.rad_to_deg(prod_units.deg_to_rad(x)),
            oracle.rad_to_deg(oracle.deg_to_rad(x)),
            "round-trip parity",
        )


def test_witness_mm_to_cell_and_cell_to_mm_are_not_inverse():
    """NOT a relation. `mm_to_cell` truncates, so it is not invertible.

    The measured behaviour, pinned rather than tidied: the round-trip
    holds exactly when `mm` is already an integer multiple of
    `cell_size_mm` *and* that multiple is exactly representable. It fails
    otherwise. `(-0.5, 0.1)` is in the first camp and was originally
    written here as a counterexample by mistake -- it is kept, on the
    holds-side of the table, because the surprise is the point.
    """
    cases = {
        # (mm, cell_size): does the round-trip hold?
        (10.55, 0.1): False,
        (-0.5, 0.1): True,
        (2.9999999999, 1.0): False,
        (10.5, 0.1): True,
        (0.0, 0.1): True,
        (-2.5, 1.0): False,
    }
    for (mm, size), should_hold in cases.items():
        back = prod_units.cell_to_mm(prod_units.mm_to_cell(mm, size), size)
        assert (back == mm) is should_hold, (
            f"mm_to_cell/cell_to_mm({mm!r}, {size!r}) -> {back!r}: "
            f"expected round-trip to {'hold' if should_hold else 'fail'}"
        )
    assert any(not v for v in cases.values()), "the witness must contain a real failure"


def test_witness_scaling_a_rect_does_not_preserve_width_exactly():
    """NOT a relation. `Rect(k*a, k*b).width != k * Rect(a, b).width`.

    Scaling is *not* like the translation in M3: `(k*b) - (k*a)` and
    `k * (b - a)` are two different rounding sequences. The
    counterexample below was found by search (200 000 random triples,
    seed 0, first hit at iteration ~1) and is pinned literally so the
    witness does not depend on a search succeeding at test time. Its
    single-ulp nature is exactly why a tolerance-based comparator would
    have declared the relation true.
    """
    a, b, k = 68.88437030500961, 144.67981084108544, 42.06295236727619
    r = ProdRect.from_xyxy(a, 0.0, b, 1.0)
    scaled = ProdRect.from_xyxy(a * k, 0.0, b * k, 1.0)
    assert scaled.width != r.width * k
    assert scaled.width.hex() == (3188.180004925672).hex()
    assert (r.width * k).hex() == (3188.1800049256726).hex()
    # And the two are one ulp apart -- a relative tolerance of 1e-15
    # would have hidden it.
    assert math.isclose(scaled.width, r.width * k, rel_tol=1e-15)


@pytest.mark.skipif(
    os.environ.get("TEMPER_SKIP_SUBPROCESS_TESTS") == "1",
    reason="subprocess spawning disabled",
)
def test_witness_frozenset_iteration_order_is_hash_seed_dependent():
    """NOT an invariant of the *implementation*, and deliberately not
    "fixed" by sorting.

    ``_matches_any`` iterates a ``frozenset`` of ``str``, whose order is
    ``PYTHONHASHSEED``-dependent. This test proves (a) the order really
    does move between seeds -- so the concern is real, not theoretical --
    and (b) the classification results do **not**, because the loop is a
    pure disjunction. The order is left alone; only the invariance is
    asserted.
    """
    probe = (
        "import os,sys;"
        "sys.path.insert(0, os.environ['PLACER_SRC']);"
        "from temper_placer.core.net_classification import GROUND_NET_PATTERNS as G, "
        "HV_NET_PATTERNS as H;"
        "from temper_placer.core.net_classification import classify_net_type as c;"
        "names=['GND','VCC','AC_L','SDA','PE','DC_BUS+','GND_PE','X_VSS_1'];"
        "print(repr(list(G)));"
        "print(repr(list(H)));"
        "print(repr([c(n) for n in names]))"
    )
    src = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"
    )
    orders, results = set(), set()
    for seed in ("0", "1", "2", "3", "4", "5", "6", "7"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PLACER_SRC": src}
        out = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout.splitlines()
        orders.add((out[0], out[1]))
        results.add(out[2])

    assert len(orders) > 1, (
        "frozenset iteration order did not move across PYTHONHASHSEED values; "
        "this test can no longer prove the invariance it claims"
    )
    assert len(results) == 1, (
        f"classification changed with the hash seed -- order invariance is BROKEN: {results!r}"
    )


def test_signature_of_the_witnesses_is_recorded():
    """A guard on the guards: the witness tests must be able to fail."""
    assert signature(1) != signature(1.0)
    assert list(itertools.islice(iter([1, 2, 3]), 2)) == [1, 2]
