"""Reproduction of the K3/tank3 run-B "audit lie" (issue #523 gap 2).

The placer's scoped solve for K3/tank3 produced a candidate placement
("run-B", documented in
``docs/evidence/2026-08-01-k3-runb-not-validator-clean.md``) that PASSED the
solver's own post-solve audit (``audit_domain_clearance``, center-to-center
Euclidean distance) but FAILED the real REQ-SAFE-01 gate
(``verify_iec60335_compliance``, exact copper-to-copper on pad geometry):
REQ-SAFE-01 went 3 -> 12 violations while the audit reported 0.

What is recoverable from the evidence doc:

- K3 -> board-file ``(at 63.52 51.97)`` rot 90
- C27 -> board-file ``(at 44.44 236.56)``
- The documented per-pair validator measurements (7 of the 10 pairs
  reproduce bit-exactly below).

What is NOT recoverable: the full run-B placement. The "nothing hard-pinned,
min-displacement to current" repair recipe may have moved refs other than
K3/C27; the doc records only the two targets. Empirically the three K3-side
pairs (C3/K3 5.94, K3/R60 5.07, C24/K3 4.971) are mutually inconsistent with
any single K3 position at committed positions for C3/R60/C24 (grid-searched),
so those refs moved in the real solve and their run-B positions are lost.

This test asserts what IS reproduced, exactly:

1. **The audit passes (0 violations)** -- with the scoped constraint set the
   solve would have used (``component_refs={K3, C27}`` -- the FREE set), the
   generated constraint set is just the C27<->K3 pair at the 8.0mm margin,
   whose center distance is huge, so ``audit_domain_clearance`` returns 0.
   This is the documented "audit_domain_clearance 0 violations" claim.
2. **The validator fires on the same placement** -- including the headline
   pair C27/U24 at 0.320mm copper-to-copper (documented "C27 landed 0.32mm
   from U24") despite a 15.36mm center distance that the audit accepts. A
   center-distance check cannot see this; an exact-copper check can.

The fixture is the real board (via the shared
``_real_board_fixture.load_real_board_placement``), so this test only runs
where the PCB + compiled netlist + domain manifest exist; it is a
reproduction/regression probe, not a solver-feasibility claim.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from temper_placer.placer.cp_sat.domain_clearance import (
    audit_domain_clearance,
    generate_domain_clearance_constraints,
)
from temper_placer.requirements.validators.clearance import verify_iec60335_compliance

from ._real_board_fixture import RealBoardUnavailable, load_real_board_placement

# Documented run-B targets (board-file "at x y" frame).
RUNB_K3 = (63.52, 51.97)  # rot 90 (unchanged from committed board)
RUNB_C27 = (44.44, 236.56)
BOARD_ORIGIN = (20.0, 20.0)  # parser subtracts (20,20); see handoff §6 trap

# The scoped FREE set the run-B solve used (evidence doc step 3).
RUNB_FREE_REFS = {"K3", "C27"}

# Documented per-pair validator measurements that reproduce bit-exactly when
# K3/C27 are moved and everything else stays at its committed position.
# (ref_a, ref_b) -> documented measured mm. Only the C27 pairs are exact:
# the three K3-side pairs are not reproduced (those refs moved in the solve).
DOCUMENTED_EXACT_PAIRS = {
    ("C27", "U24"): 0.32,
    ("C27", "R1"): 1.528,
    ("C27", "Q1"): 5.123,
    ("C27", "R48"): 5.675,
    ("C27", "R63"): 6.683,
    ("C27", "U10"): 6.87,
    ("C27", "D4"): 4.63,
}


@pytest.fixture(scope="module")
def runb_placement() -> tuple[dict[str, Any], dict[str, Any]]:
    """The run-B candidate placement plus its voltage-domain map."""
    try:
        placement, voltage_domains, _stats = load_real_board_placement()
    except RealBoardUnavailable as exc:
        pytest.skip(f"{exc} (run `make netlist` first)")
    import copy

    out = copy.deepcopy(placement)
    for comp in out["components"]:
        if comp["ref"] == "K3":
            comp["position"] = (RUNB_K3[0] - BOARD_ORIGIN[0], RUNB_K3[1] - BOARD_ORIGIN[1])
        elif comp["ref"] == "C27":
            comp["position"] = (RUNB_C27[0] - BOARD_ORIGIN[0], RUNB_C27[1] - BOARD_ORIGIN[1])
    return out, dict(voltage_domains)


def _pair_distances(placement: dict[str, Any]) -> dict[tuple[str, str], float]:
    """{unordered pair: min measured mm} over all validator violations."""
    voltage_domains = {n: placement["nets"][n]["domain"] for n in placement["nets"]}
    result = verify_iec60335_compliance(placement, voltage_domains)
    out: dict[tuple[str, str], float] = {}
    for v in result.violations:
        if v.ref_a is None or v.ref_b is None or v.measured_mm is None:
            continue
        key = tuple(sorted((v.ref_a, v.ref_b)))
        out[key] = min(out.get(key, math.inf), v.measured_mm)
    return out


def test_runb_scoped_audit_is_clean(
    runb_placement: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """The solver's own post-solve audit reports 0 on the run-B candidate.

    With the scoped FREE-set constraint generation the solve used
    (``component_refs={K3, C27}``), exactly one domain-clearance constraint is
    generated (C27<->K3 at the 8.0mm bar) and its center distance is large, so
    ``audit_domain_clearance`` -- the center-to-center recompute the solver
    gates on -- returns 0. This is the documented "audit_domain_clearance 0
    violations" claim, reproduced.
    """
    runb, voltage_domains = runb_placement
    constraints = generate_domain_clearance_constraints(
        runb, voltage_domains, component_refs=set(RUNB_FREE_REFS)
    )
    positions = {c["ref"]: c["position"] for c in runb["components"]}
    audit = audit_domain_clearance(constraints, positions)

    assert constraints, "scoped FREE set should still generate the C27<->K3 pair"
    assert all(c.a == "C27" and c.b == "K3" for c in constraints)
    assert audit == [], (
        f"center-distance audit must pass on the run-B candidate, but flagged "
        f"{[(v.ref_a, v.ref_b, round(v.actual_mm, 3)) for v in audit]}"
    )


def test_runb_validator_fires_headline_pair(
    runb_placement: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """The same placement fails the exact-copper validator on C27/U24.

    Center distance C27<->U24 is 15.36mm (audit-clean against the 8.0mm bar),
    but the axial tank cap C27's copper extends ~20mm from its origin toward
    U24, so copper-to-copper is 0.320mm -- the documented "C27 landed 0.32mm
    from U24" headline, reproduced to sub-micron precision.
    """
    runb, _voltage_domains = runb_placement
    distances = _pair_distances(runb)
    pair = ("C27", "U24")
    assert pair in distances, (
        f"C27/U24 must be a validator violation on the run-B candidate; "
        f"got pairs {sorted(distances)}"
    )
    assert distances[pair] == pytest.approx(DOCUMENTED_EXACT_PAIRS[pair], abs=0.001)

    # The audit side: center distance >= 8.0 (the constraint the audit would
    # apply) while copper < 8.0 -- the lie in one pair.
    c27 = next(c for c in runb["components"] if c["ref"] == "C27")
    u24 = next(c for c in runb["components"] if c["ref"] == "U24")
    center = math.dist(c27["position"], u24["position"])
    assert center >= 8.0
    assert distances[pair] < 8.0
    assert center - distances[pair] > 10.0


def test_runb_validator_reproduces_documented_exact_pairs(
    runb_placement: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """Every C27-side pair documented in the evidence doc reproduces exactly.

    Moving only K3/C27 to their documented run-B targets and re-measuring with
    the real-board validator yields the documented values for all seven C27
    pairs (the doc's other three pairs involve K3 and are NOT reproduced: C3/
    R60/C24 moved during the real solve and their run-B positions are lost).
    """
    runb, _voltage_domains = runb_placement
    distances = _pair_distances(runb)
    for pair, documented_mm in DOCUMENTED_EXACT_PAIRS.items():
        assert pair in distances, (
            f"documented pair {pair} ({documented_mm}mm) not flagged in "
            f"reconstruction; got {sorted(distances)}"
        )
        assert distances[pair] == pytest.approx(documented_mm, abs=0.001), (
            f"reconstructed {pair} = {distances[pair]:.4f}mm vs documented "
            f"{documented_mm}mm"
        )


def test_runb_validator_total_exceeds_documented(
    runb_placement: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """The validator fires at least as many inter-component records as the doc.

    The doc measured 12 records / 9 pairs on the FULL run-B placement (which
    moved additional refs). The reconstruction -- only K3/C27 moved -- cannot
    reproduce the exact tally (some refs landed differently in the real
    solve), but it must not UNDER-report: the run-B candidate is strictly
    worse than the committed board on the exact-copper gate. Committed board
    is 3 records / 1 pair (all K3-intra); the candidate must exceed that.
    """
    runb, _voltage_domains = runb_placement
    distances = _pair_distances(runb)
    assert len(distances) >= 9, (
        f"reconstruction reports only {len(distances)} violating pairs; the "
        f"documented run-B candidate had 9 pairs (12 records)"
    )
