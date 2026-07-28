"""
Real-board placement fixture for REQ-SAFE-01 integration tests.

Combines two real, independently-sourced data sets rather than inventing a
synthetic fixture:

- Component **positions** come from the committed, routed board,
  ``pcb/temper.kicad_pcb`` (via ``temper_placer.io.kicad_parser.parse_kicad_pcb``).
  Positions are keyed by reference designator, which is stable across a net
  rename -- unlike net names, a ref does not change when the schematic is
  edited to rename or re-scope a net.
- Net **domain classification** comes from ``elec/domain_manifest.yaml``,
  parsed by (reusing, not re-deriving) ``scripts/check_domain_partition.py``'s
  own manifest loader and netlist parser, cross-checked against
  ``elec/build/default.net`` (produced by ``make netlist`` from the current
  ``elec/src/*.ato``).

**2026-07-27 rewrite -- why this no longer hand-maintains its own net list.**
This module used to carry its own, hand-picked ``_NET_DOMAINS`` dict of just
10 net names (``gnd``, ``+15V``, ``+3V3``, ``ZCD_ISO``, ``+170V_BUS``,
``PWR_RTN``, ``DC_BUS_RTN``, ``zcd``, ``ac_l``, ``ac_n``) -- a strict subset
of the 39 (now 47; see below) nets ``elec/domain_manifest.yaml`` already
declares and a human already reviewed. That gap was measured directly (not
assumed) in
``docs/evidence/2026-07-27-domain-classification-coverage.md``: with the
10-net list, only 127 of 170 components (74.7%) had any pin on a classified
net -- the other 43 were invisible to
``verify_iec60335_compliance``/``generate_domain_clearance_constraints``
entirely (no HV/SELV pair naming them, so no clearance constraint could ever
be generated for them, regardless of how close they sat to a mains-connected
part). Maintaining a second, independently-curated net-domain map next to
``elec/domain_manifest.yaml`` is exactly the kind of duplicated, driftable
classification this project's own tools warn against elsewhere (see
``domain_clearance.py``'s "Reuse, not reinvention" precedent for the
validator/constraint-generator split). This module now derives its
``VoltageDomain`` map from the manifest directly, so both mechanisms
(``check_domain_partition.py``'s galvanic-isolation graph check and this
suite's physical clearance/creepage check) are answering "which domain is
net X in?" from one, human-reviewed source, not two that can quietly
disagree.

**HV domain sub-classification.** ``elec/domain_manifest.yaml`` has only two
top-level domains, ``HV`` and ``SELV`` -- it does not distinguish
``VoltageDomain.MAINS`` from ``VoltageDomain.DC_BUS`` the way this
validator's IEC60335_REQUIREMENTS matrix can. This loader maps ``ac_l``/
``ac_n`` (the only genuinely raw-AC-line nets) to ``MAINS`` and every other
declared HV net to ``DC_BUS``. This is a safe simplification, not a
loosening: every matrix row that applies to ``MAINS`` also applies
identically to ``DC_BUS`` at the same clearance/creepage values (3.0/4.0mm
basic, 6.0/8.0mm reinforced) -- the only row that distinguishes them
(``MAINS``, ``ISOLATED``, ``REINFORCED``) is never populated by this loader
either way, because no net in this design maps 1:1 to "the floating side of
a declared isolator" (``VoltageDomain.ISOLATED`` stays empty, same as
before this rewrite -- an honest, still-open gap, not silently closed).
``VoltageDomain.BOOTSTRAP`` is likewise unused: IEC60335_REQUIREMENTS has no
row referencing it, so classifying a net as BOOTSTRAP would be equivalent to
leaving it unclassified for every check this validator actually runs; DC_BUS
is used instead so those nets (e.g. ``+15V_LS``, which floats on
``DC_BUS_RTN`` per the manifest's own comment) are at least covered by the
DC_BUS<->LV_CONTROL rows rather than falling through entirely.

**Unclassified components are no longer invisible.** The prior version of
this loader built ``placement["components"]`` from ONLY the components that
matched a classified net -- any component whose pins were all on
unclassified nets was silently dropped, before ``verify_iec60335_compliance``
even ran. That is the vacuity mechanism this rewrite closes: ``stats`` below
now also reports ``unclassified_components`` (every ref with a PCB position
that matched zero declared nets) and ``proximity_findings`` -- for each
unclassified component, its straight-line distance to the nearest
HV-domain-classified component, computed directly from the same PCB
positions this fixture already loads, INDEPENDENT of whether that pair would
ever have been paired by ``_domain_boundary_pairs`` (it wouldn't -- neither
side is a declared domain, so no constraint/check would ever see it). A
finding within ``MAX_IEC_MARGIN_MM`` (the largest clearance/creepage minimum
in ``IEC60335_REQUIREMENTS``, currently 8.0mm) of a real HV-classified
component is a live, real, currently-uncovered candidate violation and must
not be silently dropped. The one narrow exemption applied here (see
``exempt_pairs`` below) is pairs of components that are BOTH members of the
SAME already-declared ``protective_impedance_chains`` entry in the
manifest -- their proximity is governed by that chain's own,
separately-verified construction/redundancy requirement
(``scripts/check_domain_partition.py::check_chain_integrity``), not an
unexamined domain crossing; declaring this exemption does not raise a
margin, narrow a domain, or hand-pick a ref pair with no justification -- it
follows structurally from a manifest entry that already exists, with its own
arithmetic and single-fault analysis, for an unrelated reason (galvanic
isolation, not PCB clearance).

Full derivation, counts, and the falsifier this rewrite tested against:
docs/evidence/2026-07-27-domain-classification-coverage.md.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

from temper_placer.io.kicad_parser import parse_kicad_pcb
from tests.requirements.validators.clearance import IEC60335_REQUIREMENTS, VoltageDomain

_REPO_ROOT = Path(__file__).resolve().parents[5]
_PCB_PATH = _REPO_ROOT / "pcb" / "temper.kicad_pcb"
_NETLIST_PATH = _REPO_ROOT / "elec" / "build" / "default.net"
_MANIFEST_PATH = _REPO_ROOT / "elec" / "domain_manifest.yaml"

# Cross-layer import shim, same precedent as domain_clearance.py's own
# ``tests/`` shim: ``scripts/`` is not an installed package, so make it
# importable here rather than re-implementing its netlist/manifest parsers.
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from check_domain_partition import (  # noqa: E402
    GateError,
    Manifest,
    Netlist,
    build_name_to_code,
    load_manifest,
    parse_netlist,
    resolve_chain_refs,
)

# The single margin this fixture's proximity check holds every unclassified
# component to: the largest clearance/creepage minimum anywhere in the
# matrix. Computed from the matrix itself (not hardcoded) so it cannot
# silently drift from IEC60335_REQUIREMENTS if that table is ever edited.
MAX_IEC_MARGIN_MM = max(
    max(row["min_clearance_mm"], row["min_creepage_mm"]) for row in IEC60335_REQUIREMENTS.values()
)

_MAINS_NETS = {"ac_l", "ac_n"}
_HV_DOMAINS = {VoltageDomain.MAINS, VoltageDomain.DC_BUS, VoltageDomain.BOOTSTRAP}

# The net set this fixture's RETURNED placement/voltage_domains (the ones
# verify_iec60335_compliance is actually asserted against in
# test_temper_board_clearance_compliance) is restricted to -- unchanged from
# this fixture's pre-2026-07-27 behaviour, and DELIBERATELY not widened to
# the full elec/domain_manifest.yaml declaration.
#
# This is not a loophole: widening it was tried directly (not assumed
# harmless) and measured to surface 17 real, previously-invisible
# clearance/creepage violations across 9 component pairs -- see
# docs/evidence/2026-07-27-domain-classification-coverage.md sec 5. Those
# violations are REAL (the board's placement was solved with knowledge of
# only these 10 nets' domain boundaries, so of course it does not satisfy
# margins against boundaries it never knew existed) and are reported in
# full in that evidence doc, not hidden -- but fixing them requires a
# placement re-solve, and this task's own hard constraint is that
# ``pcb/temper.kicad_pcb`` is read-only (another agent is concurrently
# routing it). Declaring the wider domain here and asserting against it
# without a corresponding re-solve would either (a) fail this invariant
# test for a reason outside this task's control, or (b) require quietly
# narrowing/allowlisting to force it back to 0 -- explicitly forbidden by
# this task. Keeping this narrower, pass/fail-tested boundary set separate
# from the FULL coverage/proximity reporting below (which uses every
# declared net) is what lets this fixture be completely honest about the
# gap (it is measured and reported, every run) without either silently
# hiding it or breaking an invariant this task requires to stay green.
# Widening this set is the natural next step alongside a placement
# re-solve, not a substitute for one.
_LEGACY_CLEARANCE_NETS = frozenset(
    {
        "gnd",
        "+15V",
        "+3V3",
        "ZCD_ISO",
        "+170V_BUS",
        "PWR_RTN",
        "DC_BUS_RTN",
        "zcd",
        "ac_l",
        "ac_n",
    }
)


class RealBoardUnavailable(RuntimeError):
    """Raised when the real-board fixture inputs are missing.

    Callers should ``pytest.skip`` on this, not treat it as a passing or
    failing check -- "no PCB/netlist/manifest available" is a different,
    honest condition from "zero violations found."
    """


def _domain_for_manifest_domain(manifest_domain: str, net_name: str) -> VoltageDomain:
    """Map an ``elec/domain_manifest.yaml`` domain name + net name to this
    validator's finer-grained ``VoltageDomain`` enum. See module docstring
    ("HV domain sub-classification") for why ``ac_l``/``ac_n`` alone map to
    MAINS and everything else declared HV maps to DC_BUS.
    """
    if manifest_domain == "HV":
        return VoltageDomain.MAINS if net_name in _MAINS_NETS else VoltageDomain.DC_BUS
    if manifest_domain == "SELV":
        return VoltageDomain.LV_CONTROL
    raise ValueError(
        f"elec/domain_manifest.yaml declares an unrecognized domain "
        f"{manifest_domain!r} -- this loader only knows how to map HV/SELV "
        "into VoltageDomain; update _domain_for_manifest_domain if a third "
        "domain is ever added to the manifest."
    )


def _net_to_refs(netlist: Netlist) -> dict[str, set[str]]:
    """{net_name: {ref, ...}} for EVERY compiled net, not just declared
    ones -- used both to resolve declared nets to their touching refs and to
    report which (undeclared) nets an unclassified component sits on."""
    out: dict[str, set[str]] = {}
    for code, nodes in netlist.net_nodes.items():
        name = netlist.nets[code]
        out.setdefault(name, set()).update(ref for ref, _pin in nodes)
    return out


def _chain_sibling_exempt_pairs(
    netlist: Netlist, manifest: Manifest
) -> set[frozenset[str]]:
    """Every unordered ref pair that are both members of the SAME declared
    ``protective_impedance_chains`` entry. See module docstring's
    "Unclassified components are no longer invisible" section for why this
    is the one narrow exemption applied to the proximity check below."""
    chain_refs = resolve_chain_refs(netlist, manifest.chains)
    pairs: set[frozenset[str]] = set()
    for refs in chain_refs.values():
        for i in range(len(refs)):
            for j in range(i + 1, len(refs)):
                pairs.add(frozenset({refs[i], refs[j]}))
    return pairs


def load_real_board_placement() -> tuple[dict[str, Any], dict[str, VoltageDomain], dict[str, Any]]:
    """Build a (placement, voltage_domains, stats) tuple from the real board.

    Returns:
        placement: {"components": [...], "nets": {...}} in the shape
            consumed by check_domain_clearance / check_creepage_path /
            verify_iec60335_compliance. ``components`` includes only
            CLASSIFIED components (a pin on >=1 declared net), matching
            what those validators need -- unclassified components are
            reported separately (see ``stats``), not silently included with
            a fabricated domain.
        voltage_domains: {net_name: VoltageDomain} for the classified nets
            actually present, for verify_iec60335_compliance's second arg.
        stats: diagnostic counts (refs matched, nets classified, coverage
            ratio, unclassified-component HV-proximity findings) for
            reporting -- not used by the validators themselves, but is what
            the caller must inspect and print before trusting any 0-error
            result (see test_temper_board_clearance_compliance).

    Raises:
        RealBoardUnavailable: if the PCB, compiled netlist, or domain
            manifest is missing (e.g. ``make netlist`` was never run).
            Callers should ``pytest.skip`` on this, not treat it as a
            passing or failing check.
    """
    if not _PCB_PATH.exists():
        raise RealBoardUnavailable(f"PCB not found: {_PCB_PATH}")
    if not _NETLIST_PATH.exists():
        raise RealBoardUnavailable(
            f"Netlist not found: {_NETLIST_PATH} -- run `make netlist` first."
        )
    if not _MANIFEST_PATH.exists():
        raise RealBoardUnavailable(f"Domain manifest not found: {_MANIFEST_PATH}")

    # Intentionally NOT wrapped in try/except GateError: a GateError here
    # (e.g. a declared net that no longer exists in the compiled netlist)
    # means the manifest and the compiled design have drifted apart -- a
    # real defect that must fail this test loudly, not be swallowed into a
    # skip (which would look identical to "everything is fine, nothing to
    # check").
    netlist = parse_netlist(_NETLIST_PATH)
    manifest = load_manifest(_MANIFEST_PATH)
    name_to_code = build_name_to_code(netlist)

    net_domains_full: dict[str, VoltageDomain] = {}
    for domain_name, net_names in manifest.domains.items():
        for n in net_names:
            if n in name_to_code:  # net exists in this compiled build
                net_domains_full[n] = _domain_for_manifest_domain(domain_name, n)
    # PROMOTED 2026-07-27: the hard check now runs on the FULL declared set,
    # not the 10-net legacy subset.
    #
    # _LEGACY_CLEARANCE_NETS' own docstring names the precondition for this:
    # "Widening this set is the natural next step alongside a placement
    # re-solve, not a substitute for one." That re-solve has now happened --
    # the board was re-placed against the full 47-net classification (11,725
    # constraints, up from 7,843) and the 17 previously-invisible violations
    # went to 0, with the R24 post-solve audit clean over 12,409 constraints.
    # See docs/evidence/2026-07-27-clearance-resolve-full-coverage.md.
    #
    # Keeping the narrow set after the re-solve would mean the hard assertion
    # still inspected 10 of 48 declared nets while the board is now actually
    # compliant across all of them -- i.e. the subset blindness this fixture
    # was rewritten to eliminate, preserved for no remaining reason. It also
    # left safety.uvlo_logic-line (TP3) unclassified, which is what
    # TestRealBoardTP3Coverage catches.
    net_domains_legacy = dict(net_domains_full)

    all_net_to_refs = _net_to_refs(netlist)
    pcb_result = parse_kicad_pcb(_PCB_PATH)
    ref_to_position = {
        c.ref: c.initial_position
        for c in pcb_result.netlist.components
        if c.initial_position is not None
    }

    def _build_placement(
        net_domains: dict[str, VoltageDomain],
    ) -> tuple[dict[str, Any], dict[str, VoltageDomain], dict[str, list[str]], int]:
        ref_to_domain_nets: dict[str, list[str]] = {}
        classified_nets_present: dict[str, VoltageDomain] = {}
        for net_name, domain in net_domains.items():
            refs = all_net_to_refs.get(net_name)
            if not refs:
                continue  # net not present in this build; skip rather than guess
            classified_nets_present[net_name] = domain
            for ref in sorted(refs):
                ref_to_domain_nets.setdefault(ref, []).append(net_name)

        components: list[dict[str, Any]] = []
        matched = 0
        for ref, position in ref_to_position.items():
            nets = ref_to_domain_nets.get(ref)
            if not nets:
                continue
            matched += 1
            components.append({"ref": ref, "position": position, "nets": nets})

        nets_dict = {name: {"domain": d} for name, d in classified_nets_present.items()}
        return (
            {"components": components, "nets": nets_dict},
            dict(classified_nets_present),
            ref_to_domain_nets,
            matched,
        )

    # ``placement``/``voltage_domains`` (the tuple this function returns) use
    # the LEGACY, narrower net set -- see _LEGACY_CLEARANCE_NETS docstring
    # for why. This is what verify_iec60335_compliance is actually asserted
    # against, so its result is unchanged by this rewrite.
    placement, voltage_domains, ref_to_domain_nets_legacy, matched_refs_legacy = _build_placement(
        net_domains_legacy
    )

    # The FULL manifest-derived classification -- used for coverage
    # reporting and the unclassified-component HV-proximity check below,
    # and exposed via stats["full_placement"]/["full_voltage_domains"] so a
    # caller can optionally run verify_iec60335_compliance against it too
    # (informationally; see test_temper_board_clearance_compliance).
    full_placement, full_voltage_domains, ref_to_domain_nets_full, matched_refs_full = (
        _build_placement(net_domains_full)
    )

    # --- Coverage + unclassified-component HV-proximity data (FULL set) ---
    all_refs_with_pos = set(ref_to_position)
    classified_refs_full = {c["ref"] for c in full_placement["components"]}
    unclassified_refs = sorted(all_refs_with_pos - classified_refs_full)

    ref_to_instance_path = {ref: comp.instance_path for ref, comp in netlist.components.items()}
    ref_to_all_nets: dict[str, list[str]] = {}
    for net_name, refs in all_net_to_refs.items():
        for ref in refs:
            ref_to_all_nets.setdefault(ref, []).append(net_name)

    hv_refs_with_pos = sorted(
        ref
        for ref in classified_refs_full
        if ref in ref_to_position
        and any(
            net_domains_full.get(n) in _HV_DOMAINS for n in ref_to_domain_nets_full.get(ref, [])
        )
    )

    exempt_pairs = _chain_sibling_exempt_pairs(netlist, manifest)

    proximity_findings: list[dict[str, Any]] = []
    for ref in unclassified_refs:
        pos = ref_to_position[ref]
        best_dist: float | None = None
        best_ref: str | None = None
        for href in hv_refs_with_pos:
            if href == ref:
                continue
            d = math.dist(pos, ref_to_position[href])
            if best_dist is None or d < best_dist:
                best_dist = d
                best_ref = href
        if best_dist is None or best_ref is None:
            continue  # no HV-classified component with a position at all
        exempt = frozenset({ref, best_ref}) in exempt_pairs
        proximity_findings.append(
            {
                "ref": ref,
                "instance_path": ref_to_instance_path.get(ref, ""),
                "nets": sorted(ref_to_all_nets.get(ref, [])),
                "nearest_hv_ref": best_ref,
                "nearest_hv_instance_path": ref_to_instance_path.get(best_ref, ""),
                "distance_mm": best_dist,
                "exempt": exempt,
                "exempt_reason": (
                    f"{ref} and {best_ref} are both members of the same "
                    "declared protective_impedance_chains entry in "
                    "elec/domain_manifest.yaml -- governed by that chain's "
                    "own construction check "
                    "(scripts/check_domain_partition.py::check_chain_integrity), "
                    "not an unexamined crossing"
                )
                if exempt
                else None,
            }
        )
    proximity_findings.sort(key=lambda f: f["distance_mm"])

    declared_nets_total = sum(len(v) for v in manifest.domains.values())
    total_components = len(all_refs_with_pos)

    stats = {
        "pcb_components": len(ref_to_position),
        "netlist_components": len(netlist.components),
        "netlist_refs_on_classified_nets": len(ref_to_domain_nets_legacy),
        "matched_components_in_placement": matched_refs_legacy,
        "classified_nets_present": sorted(voltage_domains),
        "classified_nets_requested_but_absent": sorted(
            set(net_domains_legacy) - set(voltage_domains)
        ),
        # --- Full-manifest-derived numbers (the honest, whole-board
        # picture; see module docstring) ---
        "full_placement": full_placement,
        "full_voltage_domains": full_voltage_domains,
        "matched_components_in_placement_full": matched_refs_full,
        "classified_nets_present_full": sorted(full_voltage_domains),
        "declared_nets_total": declared_nets_total,
        "compiled_nets_total": len(netlist.nets),
        "unclassified_nets_total": len(netlist.nets) - len(full_voltage_domains),
        "total_components": total_components,
        "unclassified_components": unclassified_refs,
        "unclassified_components_count": len(unclassified_refs),
        "coverage_ratio": (matched_refs_full / total_components) if total_components else 0.0,
        "max_iec_margin_mm": MAX_IEC_MARGIN_MM,
        # Every unclassified component's distance to its nearest
        # HV-classified neighbour, sorted closest-first, regardless of
        # distance -- the caller (test_temper_board_clearance_compliance)
        # is the one that decides which of these count as a hard failure
        # (distance_mm < max_iec_margin_mm and not exempt), so the margin
        # itself lives in one place, not duplicated here.
        "proximity_findings": proximity_findings,
    }
    return placement, voltage_domains, stats
