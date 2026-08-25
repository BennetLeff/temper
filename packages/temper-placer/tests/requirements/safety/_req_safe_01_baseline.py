"""The committed board's measured REQ-SAFE-01 state, stratified by insulation class.

Why this exists
---------------
Four real-board safety tests asserted the board was REQ-SAFE-01 **clean
(0/0)**: ``test_clearance.py::test_temper_board_clearance_compliance``,
``test_clearance_copper.py::test_k1_is_a_genuine_creepage_violation_after_the_400v_correction``
and both ``test_runb_audit_lie.py`` board checks. That baseline was measured
on the wave-2 written board (2026-08-02,
``docs/evidence/2026-08-02-k3-swap-and-board-write.md``) under the **PD2
8.0mm** reinforced-creepage target adopted 2026-07-30.

Two threshold decisions have landed since, and neither moved a single pad:

* **#1229 (2026-08-15)** restored **PD3 / 12.6mm** reinforced creepage.
  ``docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md`` records the
  reasoning: PD3 governs the as-built, forced-air-vented, compartment-less
  board, and the sealed compartment PD2 needs is unbuilt.
* **#1226** raised **FUNCTIONAL** creepage 1.0mm -> 1.8mm.

The board therefore measures 69 violations against a baseline of 0 -- while
being, geometrically, very close to the board that measured 0. The decisive
figure: of the 32 inter-component REINFORCED violations, **28 would clear at
the superseded PD2 8.0mm bar**; only 4 are short even of 8.0mm. The bulk of
this is two documented threshold raises surfacing geometry that was always
there, not new damage.

Why stratified, and not one number
----------------------------------
A single "69" or "63 pairs" ceiling would be the wrong instrument. It would
lump a 0.650mm FUNCTIONAL gap (same-domain, worst offender on the board)
together with a REINFORCED mains<->SELV barrier, and let either grow into
the other's slack. The classes have different consequences, different
governing figures, and different owners. Pinning per stratum means a
regression in one cannot hide in another's headroom.

Contract
--------
EXACT match, both directions. A stratum growing is a regression. A stratum
shrinking is an improvement that must be recorded here, so the pin stays
tight and the next reader sees today's truth rather than a historical high
water mark. Either way ``assert_req_safe_01_at_baseline`` names the stratum
and the direction it moved.

This pins DEBT, not correctness. It is not an assertion that the board is
safe; it is an assertion that the board's measured shortfall is exactly the
documented one and has not grown. The reinforced entries in particular are
live, placement-fixable debt -- see #1471, #1490 and the K1 findings.
"""

from __future__ import annotations

from typing import Any

# (metric, insulation_type, required_mm, pair_kind) -> count.
# Measured 2026-08-25 on pcb/temper.kicad_pcb via verify_iec60335_compliance.
REQ_SAFE_01_BASELINE: dict[tuple[str, str, float, str], int] = {
    # Same-domain functional insulation. #1226 raised this bar 1.0 -> 1.8mm.
    # 28 -> 27 with the C6 move in this PR.
    ("creepage", "FUNCTIONAL", 1.8, "inter"): 27,
    # The mains<->SELV reinforced barrier at the PD3 12.6mm figure (#1229).
    # 32 -> 31: the C6 move alone took this to 34 (it landed C6 nearer R6 at
    # 7.231mm and R23 at 7.598mm), and the R56 move more than pays that back.
    ("creepage", "REINFORCED", 12.6, "inter"): 31,
    # Package-intrinsic straddlers: U6 8.100mm, T1/T2 9.100mm. Placement
    # CANNOT fix these -- a footprint carries its own pads. They are the open
    # Question A of docs/evidence/
    # 2026-08-14-certification-lab-package-pd3-and-60664-4.md.
    ("creepage", "REINFORCED", 12.6, "intra"): 3,
    # 3 -> 1: two of these were K1<->R56, cleared by the R56 move.
    ("creepage", "BASIC", 6.3, "inter"): 1,
    # Clearance (through-air), not creepage: pollution-degree INDEPENDENT, so
    # no PD decision can explain or excuse one. 3 -> 1: the K1<->R56 breach at
    # 5.036mm against the 6.0mm floor is gone. That was the one finding on
    # this board that no threshold change could account for.
    ("clearance", "REINFORCED", 6.0, "inter"): 1,
}

REQ_SAFE_01_BASELINE_TOTAL = sum(REQ_SAFE_01_BASELINE.values())  # 63


def req_safe_01_strata(result: Any) -> dict[tuple[str, str, float, str], int]:
    """Bucket a ``verify_iec60335_compliance`` result by insulation class."""
    strata: dict[tuple[str, str, float, str], int] = {}
    for v in result.violations:
        key = (
            v.metric,
            str(v.insulation_type).rsplit(".", 1)[-1],
            v.required_mm,
            "intra" if v.ref_a == v.ref_b else "inter",
        )
        strata[key] = strata.get(key, 0) + 1
    return strata


def assert_req_safe_01_at_baseline(result: Any, *, context: str) -> None:
    """Fail unless the board's measured REQ-SAFE-01 strata match the pin exactly.

    ``context`` names the caller in the failure message, since four tests
    share this pin and the message should say which one tripped.
    """
    actual = req_safe_01_strata(result)
    if actual == REQ_SAFE_01_BASELINE:
        return

    grew, shrank, appeared, vanished = [], [], [], []
    for key in sorted(set(actual) | set(REQ_SAFE_01_BASELINE)):
        want = REQ_SAFE_01_BASELINE.get(key, 0)
        got = actual.get(key, 0)
        if got == want:
            continue
        label = f"{key[0]}/{key[1]}/{key[2]}mm/{key[3]}"
        if want == 0:
            appeared.append(f"{label}: NEW stratum, {got}")
        elif got == 0:
            vanished.append(f"{label}: gone (was {want})")
        elif got > want:
            grew.append(f"{label}: {want} -> {got}  (+{got - want})")
        else:
            shrank.append(f"{label}: {want} -> {got}  ({got - want})")

    lines = [
        f"{context}: the board's REQ-SAFE-01 strata no longer match the pin in "
        f"tests/requirements/safety/_req_safe_01_baseline.py "
        f"(total {sum(actual.values())} vs pinned {REQ_SAFE_01_BASELINE_TOTAL})."
    ]
    if grew or appeared:
        lines.append(
            "  REGRESSION -- more violations than the documented debt. Fix the "
            "board; do not raise the pin to match:"
        )
        lines += [f"    {x}" for x in grew + appeared]
    if shrank or vanished:
        lines.append(
            "  IMPROVEMENT -- fewer violations than pinned. Lower the pin to "
            "lock it in, so the next regression is caught against today's "
            "truth rather than a historical high water mark:"
        )
        lines += [f"    {x}" for x in shrank + vanished]
    raise AssertionError("\n".join(lines))


# ---------------------------------------------------------------------------
# Companion pin: unclassified components sitting inside the largest IEC margin
# of a declared-HV component.
# ---------------------------------------------------------------------------
#
# Same root cause as the strata above, and the same PD3 story: the margin this
# is compared against IS the reinforced figure, so it moved 8.0 -> 12.6mm with
# #1229. All three of these clear the superseded PD2 bar with ~4mm to spare and
# miss the PD3 bar by less than 0.75mm. None of them moved.
#
# This is a PROXIMITY heuristic over *unclassified* components, not a measured
# barrier violation: it flags parts with no domain declaration that are near
# declared HV, so the question it raises is "should this part be classified?"
# rather than "is this gap too small?". Kept fail-closed on the SET so a fourth
# unclassified part drifting into the margin fails here.
PROXIMITY_BASELINE: dict[str, tuple[str, float]] = {
    # ref: (nearest declared-HV ref, measured mm)
    "R37": ("R9", 11.880),  # rtd_pan.r_high_top vs discharge.r_dis2b
    "R52": ("L1", 11.906),  # safety.ovp.r_adc_top2 vs power_in.cmc
    "R68": ("R6", 12.037),  # safety.uvlo_logic.r_hyst vs discharge.r_dis1a
}


def assert_proximity_at_baseline(findings: list[dict[str, Any]], margin_mm: float) -> str | None:
    """Return a failure string if the non-exempt proximity set moved, else None.

    Mirrors the caller's existing "collect, report together" style rather than
    asserting inline, so this finding and the strata finding stay independently
    visible instead of the first one hiding the second.
    """
    actual = {
        f["ref"]: (f["nearest_hv_ref"], round(f["distance_mm"], 3))
        for f in findings
        if not f["exempt"] and f["distance_mm"] < margin_mm
    }
    if set(actual) != set(PROXIMITY_BASELINE):
        added = sorted(set(actual) - set(PROXIMITY_BASELINE))
        gone = sorted(set(PROXIMITY_BASELINE) - set(actual))
        parts = []
        if added:
            parts.append(
                f"NEW unclassified component(s) inside the {margin_mm}mm margin: "
                + ", ".join(f"{r} at {actual[r][1]:.3f}mm from {actual[r][0]}" for r in added)
                + " -- classify them or move them; do not widen the pin"
            )
        if gone:
            parts.append(f"no longer inside the margin (record it): {', '.join(gone)}")
        return "; ".join(parts)
    for ref, (hv, mm) in sorted(PROXIMITY_BASELINE.items()):
        got_hv, got_mm = actual[ref]
        if got_hv != hv or abs(got_mm - mm) > 0.001:
            return (
                f"{ref} moved: pinned {mm:.3f}mm from {hv}, measured {got_mm:.3f}mm from {got_hv}"
            )
    return None
