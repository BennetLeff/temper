"""Differential test: deterministic _phase_zones compute, Rust vs oracle.

Wave 4, **Phase 5, final leaves**. The ``_PhasePlacementMixin._compute_wirelength``
HPWL kernel of ``temper_placer/deterministic/stages/_phase_zones.py`` moves to
the ``temper-design-bundle`` crate
(``temper_design_bundle_python.deterministic_phase``); the Python method
becomes a delegation shim. The pre-migration implementation is pinned VERBATIM
as the oracle (``_phase_zones_py_oracle.py``).

Numerical traps pinned here:
- the positions list is ``[candidate_slot]`` + every already-placed other net
  member in net_pins LIST order (duplicate refs appended per pin, NOT
  deduplicated — a net listing the same ref twice appends the position twice);
- ``component_on_net`` is ``any(ref == component_ref for ref, _ in pins)``;
  a net contributes nothing when ``len(positions) <= 1``;
- HPWL is ``(max(xs) - min(xs)) + (max(ys) - min(ys))`` with CPython
  ``min``/``max``; the fold is plain ``total_hpwl += hpwl``.
"""

from __future__ import annotations

import random

import temper_design_bundle_python as _tdb
import tests.deterministic.stages._phase_zones_py_oracle as _oracle
from tests.core._contract_canon import canon

# Rust symbol under test -- must exist or this file fails to collect (RED).
_DP = _tdb.deterministic_phase
RS_HPWL = _DP.compute_wirelength


def _assert_equal(component_ref, candidate_slot, net_pins, current_placements):
    exp = _oracle.compute_wirelength(component_ref, candidate_slot, net_pins, current_placements)
    got = RS_HPWL(component_ref, candidate_slot, net_pins, current_placements)
    assert canon(got) == canon(exp), (
        f"hpwl divergence ref={component_ref} slot={candidate_slot} "
        f"net_pins={net_pins} placements={current_placements}: "
        f"{canon(got)} vs {canon(exp)}"
    )


def test_hpwl_basic():
    _assert_equal(
        "R1",
        (5.0, 5.0),
        {"NET_A": [("R1", "1"), ("R2", "1")]},
        {"R2": (0.0, 0.0)},
    )


def test_hpwl_empty_net_pins():
    _assert_equal("R1", (5.0, 5.0), {}, {})


def test_hpwl_component_not_on_any_net():
    _assert_equal("R1", (5.0, 5.0), {"NET_A": [("R2", "1")]}, {"R2": (0.0, 0.0)})


def test_hpwl_single_position_net_contributes_zero():
    """A net where the candidate is the only member -> len(positions) == 1 ->
    no HPWL contribution."""
    _assert_equal("R1", (5.0, 5.0), {"NET_A": [("R1", "1")]}, {})


def test_hpwl_negative_and_float_coords():
    _assert_equal(
        "U1",
        (-2.5, 7.5),
        {"NET_1": [("U1", "1"), ("U2", "2"), ("U3", "3")]},
        {"U2": (-10.0, 0.0), "U3": (0.0, 12.5)},
    )


def test_hpwl_unplaced_net_members_excluded():
    """A net member NOT in current_placements is skipped -> positions has only
    the candidate -> zero contribution."""
    _assert_equal("R1", (5.0, 5.0), {"NET_A": [("R1", "1"), ("R2", "1")]}, {})


def test_hpwl_duplicate_ref_pins_append_position_twice():
    """A net listing the same ref twice appends that position twice; HPWL over
    the duplicated positions is unchanged, but the max/min scan must see both
    (order preserved, not deduplicated)."""
    _assert_equal(
        "R1",
        (5.0, 5.0),
        {"NET_A": [("R1", "1"), ("R2", "1"), ("R2", "2")]},
        {"R2": (0.0, 0.0)},
    )


def test_hpwl_multiple_nets_accumulate():
    _assert_equal(
        "U1",
        (0.0, 0.0),
        {
            "NET_A": [("U1", "1"), ("U2", "1"), ("U3", "1")],
            "NET_B": [("U1", "2"), ("U4", "2")],
        },
        {"U2": (10.0, 0.0), "U3": (10.0, 10.0), "U4": (0.0, -10.0)},
    )


def test_hpwl_candidate_only_on_one_of_two_nets():
    _assert_equal(
        "R5",
        (3.0, 3.0),
        {
            "NET_A": [("R1", "1"), ("R2", "1")],
            "NET_B": [("R5", "1"), ("R6", "1")],
        },
        {"R1": (0.0, 0.0), "R2": (1.0, 1.0), "R6": (9.0, 9.0)},
    )


def test_hpwl_int_coordinates():
    _assert_equal("R1", (5, 5), {"NET_A": [("R1", "1"), ("R2", "1")]}, {"R2": (0, 0)})


def test_hpwl_randomized():
    rng = random.Random(7)
    for _ in range(150):
        ref = f"C{rng.randint(0, 9)}"
        slot = (rng.uniform(-20, 20), rng.uniform(-20, 20))
        net_pins = {}
        for n in range(rng.randint(0, 4)):
            members = []
            for _ in range(rng.randint(1, 4)):
                members.append((f"C{rng.randint(0, 9)}", f"p{rng.randint(1, 3)}"))
            net_pins[f"NET_{n}"] = members
        placements = {
            f"C{i}": (rng.uniform(-20, 20), rng.uniform(-20, 20))
            for i in range(rng.randint(0, 10))
        }
        _assert_equal(ref, slot, net_pins, placements)


def test_hpwl_empty_slot_is_not_vacuously_zero():
    """A non-trivial input must actually exercise the HPWL path."""
    assert (
        _oracle.compute_wirelength(
            "R1",
            (5.0, 5.0),
            {"NET_A": [("R1", "1"), ("R2", "1")]},
            {"R2": (0.0, 0.0)},
        )
        > 0.0
    )
