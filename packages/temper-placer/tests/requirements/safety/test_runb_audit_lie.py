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

RE-BASELINED 2026-08-02 (wave-2 board write): the run-B candidate this file
reproduced was solved against the pre-write board. The owner-granted wave-2
write (K3 -> TE Schrack RT314012 + the evidence-validated Run-B re-solve,
docs/evidence/2026-08-02-k3-swap-and-board-write.md) superseded it: the
written board measures REQ-SAFE-01 = 0/0, and overlaying the OLD run-B
targets on the NEW board is physically meaningless (the RT314012's pad
field lands on D5 at 0.000mm). The three validator-reproduction tests below
are re-based fail-closed to assert the written board's 0/0 reality (any
fired pair fails), with the historical run-B reproduction documented as
superseded.

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
from ._req_safe_01_baseline import assert_req_safe_01_at_baseline

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
    """RE-BASELINED 2026-08-02 (wave-2 board write): the historical run-B
    candidate no longer exists.

    This test originally reproduced the documented run-B "audit lie" -- the
    pre-write scoped solve's candidate (K3 at (63.52, 51.97), C27 at
    (44.44, 236.56)) that PASSED the center-distance audit but FAILED the
    exact-copper validator, headline pair C27/U24 at 0.320mm. The
    owner-granted wave-2 write (K3 -> TE Schrack RT314012 + the
    evidence-validated Run-B re-solve,
    docs/evidence/2026-08-02-k3-swap-and-board-write.md) superseded that
    candidate: K3 now sits at (43.12, 17.92) and C27 on-board at
    (28.62, 222.0), and the written board measures REQ-SAFE-01 = 0/0. The
    overlay this test built (move K3/C27 to the OLD run-B targets on top of
    the NEW board) is physically meaningless -- the RT314012's larger pad
    field lands on top of D5 at 0.000mm -- so the documented reproduction
    is gone with the board state it was measured on.

    Re-based fail-closed: the WRITTEN board (no overlay) must be
    validator-clean -- 0 violations -- and the historical headline pair
    C27/U24 at 0.320mm must NOT reproduce (the board state it was measured
    on is gone; if it fires at the documented distance, the wave-2 write
    regressed).
    """
    # The written board itself (no overlay): validator-clean, measured 0/0.
    try:
        written, _vd, _stats = load_real_board_placement()
    except RealBoardUnavailable as exc:
        pytest.skip(f"{exc} (run `make netlist` first)")
    result = verify_iec60335_compliance(
        written, {n: written["nets"][n]["domain"] for n in written["nets"]}
    )
    # RE-PINNED 2026-08-25. This line asserted the written board was
    # REQ-SAFE-01 clean (0/0) -- a wave-2 baseline measured under the PD2
    # 8.0mm target. #1229 restored PD3/12.6mm and #1226 raised functional
    # creepage 1.0 -> 1.8mm, so the board now measures 69 without a pad
    # having moved. Pinned per insulation class instead; see
    # _req_safe_01_baseline.py for why one number would be the wrong
    # instrument. This test's OWN subject -- that the historical run-B
    # C27/U24 0.320mm headline must not reproduce -- is asserted below and
    # is unaffected.
    assert_req_safe_01_at_baseline(
        result, context="test_runb_validator_fires_headline_pair (written board)"
    )
    # The historical run-B overlay is no longer a valid reproduction: it was
    # solved against the pre-write board. On the written board it is not
    # merely wrong -- it is physically invalid (K3's RT314012 pads overlap
    # D5). The old headline pair C27/U24 no longer fires at the documented
    # distance.
    distances = _pair_distances(runb_placement[0])
    assert ("C27", "U24") not in distances or distances[("C27", "U24")] != pytest.approx(
        DOCUMENTED_EXACT_PAIRS[("C27", "U24")], abs=0.001
    ), (
        "the documented run-B C27/U24 0.32mm headline should NOT reproduce on "
        "the wave-2 written board -- the board state it was measured on is gone"
    )


def test_runb_validator_reproduces_documented_exact_pairs(
    runb_placement: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """RE-BASELINED 2026-08-02 (wave-2 board write): the documented run-B
    exact pairs no longer reproduce.

    The seven C27-side pairs in DOCUMENTED_EXACT_PAIRS were measured on the
    pre-write board with K3/C27 moved to the OLD run-B targets. The wave-2
    write moved K3 to (43.12, 17.92), C27 on-board to (28.62, 222.0), and
    re-solved the neighbourhood -- the documented pair distances are a
    property of a board state that no longer exists (the same class of
    staleness the board-dependent-test rule covers). Re-based fail-closed:
    the written board is validator-clean (0 violations), so NONE of the
    documented violating pairs can be present; if any of them fires, the
    wave-2 solve regressed and this fails.
    """
    runb, _voltage_domains = runb_placement
    distances = _pair_distances(runb)
    for pair, documented_mm in DOCUMENTED_EXACT_PAIRS.items():
        assert pair not in distances, (
            f"documented run-B pair {pair} ({documented_mm}mm) fired on the "
            f"wave-2 written board ({distances[pair]:.4f}mm) -- the wave-2 "
            f"re-solve should have cleared every one of these (the board "
            f"measures REQ-SAFE-01 0/0)"
        )


def test_runb_validator_total_exceeds_documented(
    runb_placement: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """RE-BASELINED 2026-08-02 (wave-2 board write): the documented run-B
    12-record / 9-pair violation tally no longer exists.

    The original test asserted the run-B candidate (a pre-write solve
    output) produced at least as many validator violations as the doc's 12
    records / 9 pairs -- i.e. that the candidate was strictly worse than the
    committed board. The wave-2 write replaced that candidate with a
    validator-clean placement (REQ-SAFE-01 = 0/0), so the "worse than
    committed" relation is inverted by construction: the written board IS
    the resolved state. Re-based fail-closed: the written board must have
    ZERO violating pairs (any pair fires => the wave-2 solve regressed),
    and the overlay scenario is documented as superseded.
    """
    # The written board itself (no overlay): validator-clean, measured 0/0.
    try:
        written, _vd, _stats = load_real_board_placement()
    except RealBoardUnavailable as exc:
        pytest.skip(f"{exc} (run `make netlist` first)")
    # RE-PINNED 2026-08-25, same reason as the sibling test above: the
    # "0 violating pairs" figure was a PD2-era wave-2 baseline. Pinned per
    # insulation class rather than as a pair count, so a FUNCTIONAL 1.8mm
    # regression cannot hide inside REINFORCED headroom or vice versa.
    voltage_domains = {n: written["nets"][n]["domain"] for n in written["nets"]}
    assert_req_safe_01_at_baseline(
        verify_iec60335_compliance(written, voltage_domains),
        context="test_runb_validator_total_exceeds_documented (written board)",
    )
