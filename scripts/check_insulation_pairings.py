#!/usr/bin/env python3
"""CI gate: every creepage requirement on this board must be DERIVED from a
declared, dated, digest-anchored per-pairing working voltage -- and every
pairing whose requirement is **not determinable** must be surfaced, never
given a number.

WHAT THIS GATE ENFORCES
-----------------------
1. **The declaration resolves.** ``elec/insulation_manifest.yaml`` parses,
   matches its schema, carries no placeholder verification field, is not
   STALE (its facts have not been edited since the verification digest that
   backs them), and declares a pairing for *every* unordered pair of groups
   including self-pairs. All of that is enforced in Rust
   (``packages/temper-design-bundle/src/insulation.rs``); this gate only
   reports it.

2. **Coverage is exact against ``elec/domain_manifest.yaml``.** Every net of
   that manifest's HV and SELV domains appears in exactly one insulation
   group, and no insulation group declares a net that manifest does not.
   Either direction failing is a hard error: a net in the domain manifest but
   not here has *no requirement*, and a net here but not there is a
   requirement nobody's topology claim supports.

3. **The pollution-degree selectors agree.**
   ``insulation_coordination.ENFORCED_POLLUTION_DEGREE`` against
   ``scripts/generate_kicad_dru.py``'s ``HV_CREEPAGE_ENFORCED_MM =
   HV_CREEPAGE_PD[23]_MM`` selector line -- the same line
   ``scripts/check_pd2_compartment_evidence.py`` already treats as this
   repo's PD selection point.

4. **Every live enforcement point agrees with the derivation.**
   ``isolation_constants.MIN_BARRIER_WIDTH_MM``, the CP-SAT corridor
   (``isolation_barrier.DEFAULT_CORRIDOR_WIDTH_MM``), and the KiCad DRU
   emitter's per-class figures (``generate_kicad_dru.HV_TO_LV_CREEPAGE``) are
   each re-derived here and compared. A consumer that has drifted below its
   derived figure fails this gate.

5. **INDETERMINATE IS REPORTED AND IS NOT A PASS.** This board switches at
   47 kHz (``elec/src/main.ato:134``), above IEC 60664-1 cl. 1.1.1's declared
   scope (*"rated frequencies up to 30 kHz"*), and cl. 2.3 routes
   dimensioning above it to IEC 60664-4 -- paywalled and not obtained by this
   project. Every pairing that touches the switch node or the resonant tank
   therefore has **no determinable requirement**. This gate prints each one,
   with the proven lower bound that is all we have, and exits
   ``EXIT_INDETERMINATE``.

WHY EXIT NON-ZERO ON SOMETHING NOBODY CAN FIX
---------------------------------------------
Because the alternative is worse. The only ways to make this gate green are
to obtain IEC 60664-4 (or the UL/CSA 6th Ed. >30 kHz creepage text, which the
Intertek SUN records as already written into these same clauses) and
re-derive, or to change the design so nothing above 30 kHz faces SELV. Both
are real closures. Silently applying a <=30 kHz number to a >30 kHz pairing is
not, and that is precisely how ``MIN_BARRIER_WIDTH_MM = 12.6`` came to be
enforced against a crossing needing at least 20.0 mm.

**Never make this gate pass by giving an indeterminate pairing a number.**

WHAT THIS GATE CANNOT DO
------------------------
It cannot make a working voltage true. It operates on a *claim*: that the
declared r.m.s. figures describe this circuit. It can ensure the claim is
explicit, complete, internally consistent and unchanged since it was
verified. The tank<->SELV working voltage in particular has never been
measured in this repository -- 570.5 V r.m.s. is a tank-to-*bus* figure
carried forward. That is a measurement gap, not a standards gap, and it is
cheap to close.

Exit codes
----------
0  every pairing determinable, every consumer agrees
2  usage error
3  a consumer disagrees with its derived figure, or coverage is wrong
4  the declaration could not be resolved at all (missing, stale, incomplete)
6  resolved and consistent, but at least one pairing is NOT DETERMINABLE

``--print-digest`` recomputes ``verification.declared_state_sha256`` from the
file as committed, as part of recording a real re-verification. It does not
write anything.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DOMAIN_MANIFEST = REPO_ROOT / "elec" / "domain_manifest.yaml"

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_DISAGREEMENT = 3
EXIT_UNRESOLVABLE = 4
EXIT_INDETERMINATE = 6

# Tolerance for comparing two floats that should be the same derived figure.
# Not a margin: any real disagreement is orders of magnitude above this.
_EPS = 1e-9


def _load_domain_nets(path: Path) -> tuple[set[str], set[str]]:
    """(hv, selv) exactly as ``elec/domain_manifest.yaml`` declares them.

    Exact literal net names only -- never a pattern or prefix. Same discipline
    the manifest states for itself and that
    ``scripts/check_isolation_keepout.py`` already follows.
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    domains = data["domains"]
    return set(domains["HV"]["nets"]), set(domains["SELV"]["nets"])


def _dru_pollution_degree() -> int:
    """The PD the DRU emitter selects, read from its own selector line."""
    text = (REPO_ROOT / "scripts" / "generate_kicad_dru.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD"):
            return int(stripped.rsplit("PD", 1)[1].split("_", 1)[0])
    raise RuntimeError(
        "scripts/generate_kicad_dru.py has no "
        "'HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD<n>_MM' selector line. That "
        "line is this repository's pollution-degree selection point (it is "
        "also what scripts/check_pd2_compartment_evidence.py reads); without "
        "it no pollution degree can be cross-checked and none is assumed."
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--declaration",
        type=Path,
        default=None,
        help="override elec/insulation_manifest.yaml (tests only)",
    )
    parser.add_argument(
        "--domain-manifest", type=Path, default=DOMAIN_MANIFEST
    )
    parser.add_argument(
        "--print-digest",
        action="store_true",
        help="recompute verification.declared_state_sha256 and print it",
    )
    args = parser.parse_args(argv[1:])

    import temper_design_bundle_python as tdb
    from temper_placer.core import insulation_coordination as ic

    path = ic.DECLARATION_PATH if args.declaration is None else args.declaration
    if args.print_digest:
        try:
            print(tdb.insulation_facts_digest(Path(path).read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            print(f"cannot digest {path}: {exc}", file=sys.stderr)
            return EXIT_USAGE
        return EXIT_OK

    print(f"Declaration: {path}")
    print(f"Domain manifest: {args.domain_manifest}")

    try:
        resolution = ic.resolve_declaration(path=args.declaration)
    except ic.InsulationDeclarationError as exc:
        print("=== INSULATION DECLARATION UNRESOLVABLE ===", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        print(
            "GATE RESULT: ERROR -- no creepage requirement can be derived and "
            "none is assumed. This is not a violation and not a pass.",
            file=sys.stderr,
        )
        return EXIT_UNRESOLVABLE

    problems: list[str] = []

    # -- 1. the per-pairing table ----------------------------------------
    print(
        f"\nPD{resolution.pollution_degree()}, material group "
        f"{resolution.material_group()}; verified {resolution.verified_on()} "
        f"at {resolution.measured_at_commit()[:9]}\n"
    )
    hdr = (
        f"{'pairing':24} {'class':11} {'V rms':>8} {'f (Hz)':>8} "
        f"{'table':>9} {'row':>12} {'required':>18} {'floor mm':>9}"
    )
    print(hdr)
    print("-" * len(hdr))
    for p in resolution.pairings():
        req = (
            f"{p.requirement_mm():.2f} mm"
            if p.is_determinable()
            else "NOT DETERMINABLE"
        )
        print(
            f"{p.key():24} {p.insulation():11} {p.working_voltage_vrms():8.1f} "
            f"{p.frequency_hz():8.0f} {p.table():>9} {p.voltage_range():>12} "
            f"{req:>18} {p.enforceable_floor_mm():9.2f}"
        )

    # -- 2. coverage against the domain manifest -------------------------
    try:
        hv_nets, selv_nets = _load_domain_nets(args.domain_manifest)
    except (OSError, KeyError, yaml.YAMLError) as exc:
        print(f"cannot read {args.domain_manifest}: {exc}", file=sys.stderr)
        return EXIT_UNRESOLVABLE
    declared = resolution.declared_nets()
    domain_nets = hv_nets | selv_nets
    missing = sorted(domain_nets - set(declared))
    extra = sorted(set(declared) - domain_nets)
    if missing:
        problems.append(
            f"{len(missing)} net(s) declared in {args.domain_manifest.name} have "
            f"no insulation group and therefore NO requirement: {missing}"
        )
    if extra:
        problems.append(
            f"{len(extra)} net(s) declared in the insulation manifest are not in "
            f"{args.domain_manifest.name}'s HV or SELV domains: {extra}"
        )
    for net in sorted(domain_nets & set(declared)):
        want = "HV" if net in hv_nets else "SELV"
        got = ic.net_domain(net)
        if got != want:
            problems.append(
                f"net {net!r} is {want} in {args.domain_manifest.name} but "
                f"{got} in the insulation manifest"
            )
    print(
        f"\nCoverage: {len(declared)} declared net(s) vs {len(domain_nets)} "
        f"HV+SELV net(s) in the domain manifest "
        f"({len(missing)} missing, {len(extra)} extra)."
    )

    # -- 3. pollution-degree selectors -----------------------------------
    dru_pd = _dru_pollution_degree()
    if dru_pd != ic.ENFORCED_POLLUTION_DEGREE:
        problems.append(
            f"pollution-degree selectors disagree: generate_kicad_dru.py "
            f"selects PD{dru_pd}, insulation_coordination."
            f"ENFORCED_POLLUTION_DEGREE is {ic.ENFORCED_POLLUTION_DEGREE}"
        )
    print(f"Pollution degree: DRU selects PD{dru_pd}, loader PD{ic.ENFORCED_POLLUTION_DEGREE}.")

    # -- 4. live enforcement points --------------------------------------
    from temper_placer.core.isolation_constants import (
        MIN_BARRIER_WIDTH_IS_DETERMINATE,
        MIN_BARRIER_WIDTH_MM,
    )
    from temper_placer.placer.cp_sat.isolation_barrier import DEFAULT_CORRIDOR_WIDTH_MM

    expected_barrier = resolution.barrier_floor_mm()
    print("\nEnforcement points:")
    checks: list[tuple[str, float, float]] = [
        ("isolation_constants.MIN_BARRIER_WIDTH_MM", MIN_BARRIER_WIDTH_MM, expected_barrier),
        (
            "isolation_barrier.DEFAULT_CORRIDOR_WIDTH_MM",
            DEFAULT_CORRIDOR_WIDTH_MM,
            expected_barrier + 0.5,
        ),
    ]
    dru = importlib.import_module("generate_kicad_dru")
    for name, req in sorted(dru.HV_TO_LV_CREEPAGE.items()):
        checks.append(
            (
                f"generate_kicad_dru HV_TO_LV_CREEPAGE[{name!r}]",
                dru.hv_to_lv_creepage_mm(name),
                req.floor_mm,
            )
        )
    for name, actual, expected in checks:
        ok = abs(actual - expected) <= _EPS
        # A consumer BELOW its derived figure is the failure that matters; a
        # consumer above it is conservative and merely reported. Neither is
        # silently accepted as "equal".
        print(
            f"  {'OK  ' if ok else 'DRIFT'}  {name:52} {actual:8.3f} mm "
            f"(derived {expected:.3f})"
        )
        if not ok:
            problems.append(
                f"{name} is {actual} mm but the declaration derives "
                f"{expected} mm"
            )

    # -- 5. indeterminacy -------------------------------------------------
    indeterminate = resolution.indeterminate_pairings()
    ceiling = tdb.insulation_frequency_scope_ceiling_hz()
    if indeterminate:
        print(
            f"\n=== NOT DETERMINABLE: {len(indeterminate)} pairing(s) ===\n"
            f"IEC 60664-1 cl. 1.1.1 scopes that document to rated frequencies "
            f"up to {ceiling:.0f} Hz; cl. 2.3 routes dimensioning above it to "
            f"IEC 60664-4, which is PAYWALLED and was NOT obtained. No value "
            f"is reconstructed from it."
        )
        for p in indeterminate:
            print(
                f"  {p.key():24} {p.working_voltage_vrms():7.1f} Vrms "
                f"@ {p.frequency_hz():.0f} Hz, {p.insulation()}; proven lower "
                f"bound {p.enforceable_floor_mm()} mm "
                f"({'crosses the barrier' if p.crosses_barrier() else 'same-domain'})"
            )
        print(
            "\nClearing those bounds is NOT compliance. Closing this needs "
            "IEC 60664-4 (or\nthe UL/CSA 6th Ed. >30 kHz creepage text) and a "
            "re-derivation, or a design in\nwhich nothing above 30 kHz faces "
            "SELV. Never close it by choosing a number."
        )
    print(f"\nLIMITATION: {ic.limitation()}")

    gh = get_github_summary_path()

    if problems:
        print(f"\n=== DISAGREEMENTS: {len(problems)} ===")
        for line in problems:
            print(f"  - {line}")
        print(f"\nFAILED -- {len(problems)} disagreement(s)")
        if gh:
            with open(gh, "a") as f:
                f.write(f"### Insulation Pairings Gate -- FAILED\n")
                for line in problems:
                    f.write(f"- {line}\n")
        return EXIT_DISAGREEMENT

    if indeterminate:
        msg = (
            f"INDETERMINATE -- the declaration resolves, coverage is exact, and "
            f"all {len(checks)} enforcement point(s) agree with it, but "
            f"{len(indeterminate)} pairing(s) have NO determinable requirement "
            f"(47 kHz > IEC 60664-1's {ceiling:.0f} Hz scope ceiling; "
            f"IEC 60664-4 unobtainable). This is NOT a pass."
        )
        print(f"\n{msg}")
        if gh:
            with open(gh, "a") as f:
                f.write(f"### Insulation Pairings Gate -- INDETERMINATE\n{msg}\n")
        return EXIT_INDETERMINATE

    assert MIN_BARRIER_WIDTH_IS_DETERMINATE, (
        "no pairing is indeterminate, yet MIN_BARRIER_WIDTH_IS_DETERMINATE is "
        "False -- the two are computed from the same resolution and cannot "
        "disagree"
    )
    msg = (
        f"PASSED -- {len(resolution.pairings())} pairing(s) all determinable, "
        f"coverage exact over {len(domain_nets)} net(s), "
        f"{len(checks)} enforcement point(s) agree."
    )
    print(f"\n{msg}")
    if gh:
        with open(gh, "a") as f:
            f.write(f"### Insulation Pairings Gate -- PASSED\n{msg}\n")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
