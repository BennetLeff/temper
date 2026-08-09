"""Differential test: HV/LV guard-strip partitioning decision, Rust vs oracle.

Wave 4 follow-up slice (HV/LV guard-strip partitioning). The pure compute of
``deterministic/stages/hv_lv_partition.py`` -- the safety-category
classification + creepage ``max`` loop, the width resolution, and the
per-bucket area decision of ``HvLvPartitionStage.run`` -- moves to the
``temper-design-bundle`` crate (``temper_design_bundle_python.hv_lv_partition``);
the Python module becomes a delegation shim. The pre-migration implementation
is pinned VERBATIM as the oracle (``_hv_lv_partition_py_oracle.py``).

The non-portable GEOS surface stays Python in the shim and is NOT part of the
oracle: the shapely outline polygon, ``compute_guard_strip`` (buffer /
difference), and the ``region.area`` / ``region.is_empty`` values are
marshalled across the boundary as f64/bool inputs.

R1a: floats compare via the type-carrying ``canon`` (``float.hex()``) -- never
a tolerance. The ``max`` ties and the first-failing-bucket order are pinned
with explicit cases below.

Bit-exactness notes:
- ``creepage = max(creepage, rules[n][1])`` is CPython's two-arg builtin
  ``max`` -- FIRST argument kept on ties (``host_math::py_max``).
- ``largest = max(refs, key=areas)`` is a key-based max: FIRST maximal ref
  wins on ties.
- The bucket loop checks ``("HV", hv)`` before ``("LV", lv)``; the first
  failing bucket returns ``fallback``/``raise``.
"""

from __future__ import annotations

import random

import pytest
import temper_design_bundle_python as _tdb
import tests.deterministic._hv_lv_partition_py_oracle as _oracle
from tests.core._contract_canon import canon

# Rust symbols under test -- must exist or this file fails to collect (RED).
_RS = _tdb.hv_lv_partition

_HV_NETS = {
    "DC_BUS+": ("HV", 6.0),
    "DC_BUS-": ("HV", 6.0),
    "SW_NODE": ("HV", 6.0),
    "AC_L": ("AC", 6.0),
    "AC_N": ("AC", 6.0),
}
_LV_NETS = {
    "SPI_CLK": ("LV", 0.0),
    "+3V3": ("LV", 0.0),
    "+5V": ("LV", 0.0),
    "GND": ("iso", 0.0),
}
_UNKNOWN_NET = "UNKNOWN_NET"


def _rules(**extra):
    r = dict(_HV_NETS)
    r.update(_LV_NETS)
    r.update(extra)
    return r


def _components(*ref_nets):
    return list(ref_nets)


def _assert_classify(components_nets, rules, width_mm):
    exp = _oracle.hv_lv_classify(components_nets, rules, width_mm)
    got = _RS.hv_lv_classify(components_nets, rules, width_mm)
    assert canon(exp) == canon(got), f"components_nets={components_nets} width_mm={width_mm}"


def _assert_area_check(*args):
    exp = _oracle.hv_lv_area_check(*args)
    got = _RS.hv_lv_area_check(*args)
    assert canon(exp) == canon(got), f"args={args}"


# ---------------------------------------------------------------------------
# Classification + width resolution
# ---------------------------------------------------------------------------


def test_basic_hv_ac_lv_partition():
    """The U2 fixture: Q1 (HV), D1 (AC), U_MCU (LV), J1 (LV)."""
    comps = [
        ("Q1", ["DC_BUS+"]),
        ("D1", ["AC_L"]),
        ("U_MCU", ["SPI_CLK"]),
        ("J1", ["+3V3"]),
    ]
    exp = _oracle.hv_lv_classify(comps, _rules(), None)
    got = _RS.hv_lv_classify(comps, _rules(), None)
    assert canon(exp) == canon(got)
    assert got[0] == "ok"
    assert got[1] == ["Q1", "D1"]
    assert got[2] == ["U_MCU", "J1"]
    assert got[3].hex() == 6.0.hex()  # creepage
    assert got[4].hex() == 6.0.hex()  # width = creepage


def test_dual_domain_goes_to_lv_and_is_reported():
    comps = [
        ("Q1", ["DC_BUS+"]),
        ("U_BRIDGE", ["DC_BUS+", "SPI_CLK"]),
    ]
    exp = _oracle.hv_lv_classify(comps, _rules(), None)
    got = _RS.hv_lv_classify(comps, _rules(), None)
    assert canon(exp) == canon(got)
    assert got[1] == ["Q1"]
    assert got[2] == ["U_BRIDGE"]
    assert got[5] == ["U_BRIDGE"]  # dual list feeds the shim warning


def test_unmapped_nets_default_to_lv():
    comps = [("Q1", ["DC_BUS+"]), ("R1", [_UNKNOWN_NET])]
    exp = _oracle.hv_lv_classify(comps, _rules(), None)
    got = _RS.hv_lv_classify(comps, _rules(), None)
    assert canon(exp) == canon(got)
    assert got[2] == ["R1"]  # R1 has no category -> LV bucket


def test_empty_hv_bucket_skips():
    comps = [("U_MCU", ["SPI_CLK"]), ("R1", ["+3V3"])]
    _assert_classify(comps, _rules(), None)
    got = _RS.hv_lv_classify(comps, _rules(), None)
    assert got[0] == "skip_empty"


def test_empty_lv_bucket_skips():
    comps = [("Q1", ["DC_BUS+"]), ("Q2", ["SW_NODE"])]
    got = _RS.hv_lv_classify(comps, _rules(), None)
    assert got[0] == "skip_empty"


def test_width_zero_skips():
    comps = [("Q1", ["DC_BUS+"]), ("U_MCU", ["SPI_CLK"])]
    _assert_classify(comps, _rules(), 0)
    _assert_classify(comps, _rules(), 0.0)
    got = _RS.hv_lv_classify(comps, _rules(), 0)
    assert got[0] == "skip_zero"


def test_width_override_above_creepage_wins():
    comps = [("Q1", ["DC_BUS+"]), ("U_MCU", ["SPI_CLK"])]
    _assert_classify(comps, _rules(), 10.0)
    got = _RS.hv_lv_classify(comps, _rules(), 10.0)
    assert got[0] == "ok"
    assert got[4].hex() == 10.0.hex()


def test_width_override_below_creepage_clamps_to_creepage():
    comps = [("Q1", ["DC_BUS+"]), ("U_MCU", ["SPI_CLK"])]
    _assert_classify(comps, _rules(), 3.0)
    got = _RS.hv_lv_classify(comps, _rules(), 3.0)
    assert got[4].hex() == 6.0.hex()


def test_zero_creepage_resolves_to_zero_width_skip():
    """All-HV creepage 0.0 with no explicit width -> width 0 -> skip_zero."""
    comps = [("Q1", ["DC_BUS+"]), ("U_MCU", ["SPI_CLK"])]
    rules = {**_HV_NETS, "SPI_CLK": ("LV", 0.0), "DC_BUS+": ("HV", 0.0)}
    _assert_classify(comps, rules, None)
    got = _RS.hv_lv_classify(comps, rules, None)
    assert got[0] == "skip_zero"


def test_creepage_is_max_over_hv_nets_only():
    """LV net creepage must NOT contribute; HV/AC nets' max wins."""
    rules = {
        "SW_NODE": ("HV", 8.0),
        "AC_L": ("AC", 5.0),
        "SPI_CLK": ("LV", 42.0),
    }
    comps = [("Q1", ["SW_NODE", "AC_L"]), ("U_MCU", ["SPI_CLK"])]
    _assert_classify(comps, rules, None)
    got = _RS.hv_lv_classify(comps, rules, None)
    assert got[3].hex() == 8.0.hex()


def test_creepage_tie_keeps_first_argument():
    """max(6.0, 6.0) keeps the running value -- py_max first-arg semantics."""
    rules = {"SW_NODE": ("HV", 6.0), "AC_L": ("AC", 6.0)}
    comps = [("Q1", ["SW_NODE", "AC_L"])]
    _assert_classify(comps, rules, None)
    got = _RS.hv_lv_classify(comps, rules, None)
    assert got[3].hex() == 6.0.hex()


# ---------------------------------------------------------------------------
# Area decision
# ---------------------------------------------------------------------------


def test_area_ok_when_regions_fit():
    hv, lv = ["Q1"], ["U_MCU"]
    areas = {"Q1": 144.0, "U_MCU": 64.0}
    exp = _oracle.hv_lv_area_check(hv, lv, areas, 1000.0, False, 1000.0, False, True)
    got = _RS.hv_lv_area_check(hv, lv, areas, 1000.0, False, 1000.0, False, True)
    assert canon(exp) == canon(got)
    assert got[0] == "ok"


def test_area_fallback_on_hv_bucket():
    hv, lv = ["Q_BIG"], ["U_MCU"]
    areas = {"Q_BIG": 144.0, "U_MCU": 64.0}
    _assert_area_check(hv, lv, areas, 100.0, False, 1000.0, False, True)
    got = _RS.hv_lv_area_check(hv, lv, areas, 100.0, False, 1000.0, False, True)
    assert got[0] == "fallback"
    assert got[1] == "HV"
    assert got[2] == "Q_BIG"
    assert got[3].hex() == 100.0.hex()
    assert got[4].hex() == 144.0.hex()


def test_area_raise_when_fallback_disabled():
    hv, lv = ["Q_BIG"], ["U_MCU"]
    areas = {"Q_BIG": 144.0, "U_MCU": 64.0}
    _assert_area_check(hv, lv, areas, 100.0, False, 1000.0, False, False)
    got = _RS.hv_lv_area_check(hv, lv, areas, 100.0, False, 1000.0, False, False)
    assert got[0] == "raise"
    assert got[1] == "HV"


def test_area_lv_bucket_checked_second():
    """HV fits but LV does not -> the LV bucket decides (order load-bearing)."""
    hv, lv = ["Q1"], ["U_BIG"]
    areas = {"Q1": 10.0, "U_BIG": 500.0}
    _assert_area_check(hv, lv, areas, 1000.0, False, 100.0, False, True)
    got = _RS.hv_lv_area_check(hv, lv, areas, 1000.0, False, 100.0, False, True)
    assert got[0] == "fallback"
    assert got[1] == "LV"
    assert got[2] == "U_BIG"


def test_empty_region_skips_bucket():
    """An empty region (or empty refs) is skipped before the area test."""
    hv, lv = ["Q1"], ["U_MCU"]
    areas = {"Q1": 144.0, "U_MCU": 64.0}
    _assert_area_check(hv, lv, areas, 0.0, True, 1000.0, False, True)
    got = _RS.hv_lv_area_check(hv, lv, areas, 0.0, True, 1000.0, False, True)
    assert got[0] == "ok"


def test_empty_refs_skips_bucket():
    """An empty refs bucket is skipped before the area test (the non-empty HV
    bucket must fit first)."""
    _assert_area_check(["Q1"], [], {"Q1": 10.0}, 100.0, False, 1.0, False, True)
    got = _RS.hv_lv_area_check(["Q1"], [], {"Q1": 10.0}, 100.0, False, 1.0, False, True)
    assert got[0] == "ok"


def test_largest_is_first_max_on_ties():
    """max(refs, key=area) keeps the FIRST maximal ref on an area tie."""
    hv, lv = ["A", "B"], ["U_MCU"]
    areas = {"A": 64.0, "B": 64.0, "U_MCU": 64.0}
    _assert_area_check(hv, lv, areas, 50.0, False, 1000.0, False, False)
    got = _RS.hv_lv_area_check(hv, lv, areas, 50.0, False, 1000.0, False, False)
    assert got[2] == "A"


# ---------------------------------------------------------------------------
# Randomized parity
# ---------------------------------------------------------------------------


def _rand_component(rng, ref):
    ns = []
    for net in rng.sample(list(_HV_NETS) + list(_LV_NETS) + [_UNKNOWN_NET], k=rng.randint(0, 3)):
        ns.append(net)
    return (ref, ns)


def test_classify_randomized_parity():
    rng = random.Random(20260809)
    for _ in range(400):
        comps = [_rand_component(rng, f"C{i}") for i in range(rng.randint(0, 6))]
        rules = _rules(
            **{
                "EXTRA": (rng.choice(["HV", "AC", "LV", "iso", "Signal"]), rng.uniform(0, 12.0))
            }
        )
        width_mm = rng.choice([None, None, 0, 0.0, rng.uniform(-1, 15.0)])
        _assert_classify(comps, rules, width_mm)


def test_area_check_randomized_parity():
    rng = random.Random(42)
    for _ in range(300):
        hv = [f"H{i}" for i in range(rng.randint(0, 5))]
        lv = [f"L{i}" for i in range(rng.randint(0, 5))]
        areas = {r: rng.uniform(1.0, 1000.0) for r in hv + lv}
        _assert_area_check(
            hv,
            lv,
            areas,
            rng.uniform(0.0, 2000.0),
            rng.random() < 0.3,
            rng.uniform(0.0, 2000.0),
            rng.random() < 0.3,
            rng.random() < 0.5,
        )


# ---------------------------------------------------------------------------
# Anti-vacuity: the corpus discriminates
# ---------------------------------------------------------------------------


def test_corpus_discriminates_hv_vs_lv():
    """A degenerate always-LV kernel would fail test_basic_hv_ac_lv_partition."""
    comps = [
        ("Q1", ["DC_BUS+"]),
        ("D1", ["AC_L"]),
        ("U_MCU", ["SPI_CLK"]),
        ("J1", ["+3V3"]),
    ]
    got = _RS.hv_lv_classify(comps, _rules(), None)
    assert got[1] == ["Q1", "D1"]  # HV/AC refs must land in the HV bucket


def test_corpus_discriminates_creepage():
    """A zero-creepage kernel would fail test_width_override_below_creepage_clamps."""
    comps = [("Q1", ["SW_NODE"]), ("U_MCU", ["SPI_CLK"])]
    got = _RS.hv_lv_classify(comps, _rules(), 3.0)
    assert got[0] == "ok"
    assert got[4].hex() == 6.0.hex()  # clamped to the HV creepage, not 3.0
