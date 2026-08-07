"""
Production loader for the REQ-SAFE-01 validator-shape real-board placement.

Hoisted out of ``tests/requirements/safety/_real_board_fixture.py`` (issue
#617 second half -- the CLI optimize path could not construct the
``validator_input`` placement/voltage_domains because the only loader lived
in the test tree). This module is that loader, production-owned, so the
fixture re-exports it (one loader, one derivation) and the CLI optimize path
can audit its solved placement against the same exact-copper validator the CI
gate runs.

Combines two real, independently-sourced data sets rather than inventing a
synthetic fixture:

- Component **positions** come from the committed, routed board
  (``pcb/temper.kicad_pcb``, via ``temper_placer.io.kicad_parser.parse_kicad_pcb``).
  Positions are keyed by reference designator, which is stable across a net
  rename -- unlike net names, a ref does not change when the schematic is
  edited to rename or re-scope a net.
- Net **domain classification** comes from ``elec/domain_manifest.yaml``
  (read directly, the same discipline as
  ``placer.cp_sat.isolation_barrier.load_domain_manifest_nets``), with the
  net->ref connectivity taken from the compiled design netlist
  (``elec/build/default.net``) via
  ``validation.netlist_reconciliation.parse_design_netlist`` -- the
  self-contained production parser, byte-equivalent on net->refs and
  ref->pins to ``scripts/check_domain_partition.py``'s own netlist parser
  (verified 2026-08-05 on the real netlist: 0 mismatches).

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
positions this loader already loads, INDEPENDENT of whether that pair would
ever have been paired by ``_domain_boundary_pairs`` (it wouldn't -- neither
side is a declared domain, so no constraint/check would ever see it). A
finding within ``MAX_IEC_MARGIN_MM`` (the largest clearance/creepage minimum
in ``IEC60335_REQUIREMENTS``, currently 8.0mm) of a real HV-classified
component is a live, real, currently-uncovered candidate violation and must
not be silently dropped. The one narrow exemption applied here (see
``exempt_pairs``) is pairs of components that are BOTH members of the
SAME already-declared ``protective_impedance_chains`` entry in the
manifest -- their proximity is governed by that chain's own,
separately-verified construction/redundancy requirement
(``scripts/check_domain_partition.py::check_chain_integrity``), not an
unexamined domain crossing; declaring this exemption does not raise a
margin, narrow a domain, or hand-pick a ref pair with no justification -- it
follows structurally from a manifest entry that already exists, with its own
arithmetic and single-fault analysis, for an unrelated reason (galvanic
isolation, not PCB clearance).

**Classification source is the FULL declared set.** The hard check runs on
the full ``elec/domain_manifest.yaml`` declaration (promoted 2026-07-27:
the board was re-placed against the full 47-net classification and the
previously-invisible violations went to 0 -- see
``docs/evidence/2026-07-27-clearance-resolve-full-coverage.md``). The
pre-promotion 10-net legacy subset was identical to the full set after that
re-solve, so no narrower classification survives.

Full derivation, counts, and the falsifier this rewrite tested against:
docs/evidence/2026-07-27-domain-classification-coverage.md.
"""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any

from temper_placer.core.pad_geometry import pad_bounding_radius
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.requirements.validators.clearance import (
    IEC60335_REQUIREMENTS,
    VoltageDomain,
    _CopperModel,
)
from temper_placer.validation.netlist_reconciliation import parse_design_netlist

# The single margin this loader's proximity check holds every unclassified
# component to: the largest clearance/creepage minimum anywhere in the
# matrix. Computed from the matrix itself (not hardcoded) so it cannot
# silently drift from IEC60335_REQUIREMENTS if that table is ever edited.
MAX_IEC_MARGIN_MM = max(
    max(row["min_clearance_mm"], row["min_creepage_mm"]) for row in IEC60335_REQUIREMENTS.values()
)

_MAINS_NETS = {"ac_l", "ac_n"}
_HV_DOMAINS = {VoltageDomain.MAINS, VoltageDomain.DC_BUS, VoltageDomain.BOOTSTRAP}


class RealBoardUnavailable(RuntimeError):
    """Raised when the real-board loader's inputs are missing.

    Callers decide how to treat it: the test fixture's callers
    ``pytest.skip`` on it ("no PCB/netlist/manifest available" is a
    different, honest condition from "zero violations found"), and the CLI
    optimize path logs it and proceeds byte-identical without the audit
    ("no audit inputs" is the documented skip, not a crash).
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


def _load_manifest(
    manifest_path: Path,
) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
    """Read ``elec/domain_manifest.yaml`` into (domains, chains).

    ``domains``: domain name -> [net names]. ``chains``: the raw
    ``protective_impedance_chains`` entries (each a dict carrying ``name``
    and the ordered ``chain`` instance-path list). Self-contained yaml read
    (same discipline as ``isolation_barrier.load_domain_manifest_nets`` --
    never substring or pattern match a net name against a domain). Fails
    closed on a malformed/ambiguous declaration (a net in two domains, an
    empty domain) rather than deriving a silently-wrong classification.
    """
    import yaml

    if not manifest_path.is_file():
        raise FileNotFoundError(f"domain manifest not found: {manifest_path}")
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"domain manifest must be a mapping at the top level: {manifest_path}")

    domains_raw = data.get("domains")
    if not isinstance(domains_raw, dict) or not domains_raw:
        raise ValueError(
            "domain manifest has no non-empty 'domains' mapping -- an empty "
            "or absent domain declaration must fail loudly, not classify vacuously"
        )

    domains: dict[str, list[str]] = {}
    net_owner: dict[str, str] = {}
    for domain_name, domain_body in domains_raw.items():
        if not isinstance(domain_body, dict):
            raise ValueError(f"domain {domain_name!r} must be a mapping")
        nets = domain_body.get("nets")
        if not isinstance(nets, list) or not nets:
            raise ValueError(f"domain {domain_name!r} has no non-empty 'nets' list")
        cleaned = [str(n) for n in nets]
        for n in cleaned:
            if n in net_owner:
                raise ValueError(
                    f"net {n!r} is declared under both domain {net_owner[n]!r} "
                    f"and {domain_name!r} -- a net cannot belong to two domains"
                )
            net_owner[n] = domain_name
        domains[str(domain_name)] = cleaned

    chains_raw = data.get("protective_impedance_chains")
    if chains_raw is None:
        chains_raw = []
    if not isinstance(chains_raw, list):
        raise ValueError("'protective_impedance_chains' must be a list if present")
    return domains, list(chains_raw)


def _net_to_refs(netlist: Any) -> dict[str, set[str]]:
    """{net_name: {ref, ...}} for EVERY compiled net, not just declared
    ones -- used both to resolve declared nets to their touching refs and to
    report which (undeclared) nets an unclassified component sits on."""
    out: dict[str, set[str]] = {}
    for name, nodes in netlist.nets.items():
        out.setdefault(name, set()).update(ref for ref, _pin in nodes)
    return out


def _ref_to_pins(netlist: Any) -> dict[str, list[str]]:
    """{ref: [wired pin, ...]} from the compiled netlist -- the pin-count
    evidence the chain-member two-terminal check needs."""
    out: dict[str, list[str]] = {}
    for nodes in netlist.nets.values():
        for ref, pin in nodes:
            out.setdefault(ref, []).append(pin)
    return out


def _chain_sibling_exempt_pairs(
    netlist: Any, chains: list[dict[str, Any]]
) -> set[frozenset[str]]:
    """Every unordered ref pair that are both members of the SAME declared
    ``protective_impedance_chains`` entry. See module docstring's
    "Unclassified components are no longer invisible" section for why this
    is the one narrow exemption applied to the proximity check below.

    Mirrors ``scripts/check_domain_partition.py::resolve_chain_refs``'s
    fail-closed contract: a chain member that matches no compiled component
    (or matches a part with != 2 wired pins) is a real defect -- the
    protective-impedance construction no longer exists as declared -- and
    must raise, never be silently skipped.
    """
    path_to_refs: dict[str, list[str]] = {}
    for comp in netlist.components:
        path_to_refs.setdefault(comp.instance_path, []).append(comp.ref)
    ref_to_pins = _ref_to_pins(netlist)

    pairs: set[frozenset[str]] = set()
    for chain in chains:
        if not isinstance(chain, dict):
            raise ValueError("protective_impedance_chains entry must be a mapping")
        chain_name = chain.get("name", "?")
        chain_paths = chain.get("chain")
        if not isinstance(chain_paths, list):
            raise ValueError(
                f"protective_impedance_chain {chain_name!r} has no ordered 'chain' list"
            )
        refs: list[str] = []
        for path in chain_paths:
            matches = path_to_refs.get(str(path), [])
            if not matches:
                raise ValueError(
                    f"protective_impedance_chain {chain_name!r} member {path!r} "
                    "matches no component in the netlist -- the manifest is "
                    "stale or the component was removed from the design"
                )
            if len(matches) > 1:
                raise ValueError(
                    f"protective_impedance_chain {chain_name!r} member {path!r} "
                    f"matches {len(matches)} components ({matches!r}) -- "
                    "instance paths must be unique"
                )
            ref = matches[0]
            wired = sorted(set(ref_to_pins.get(ref, [])))
            if len(wired) != 2:
                raise ValueError(
                    f"protective_impedance_chain {chain_name!r} member {path!r} "
                    f"(ref {ref}) has {len(wired)} wired pin(s) {wired}, not "
                    "exactly 2 -- chain members must be plain two-terminal "
                    "components"
                )
            refs.append(ref)
        for i in range(len(refs)):
            for j in range(i + 1, len(refs)):
                pairs.add(frozenset({refs[i], refs[j]}))
    return pairs


def _rotation_deg_for_component(comp: Any) -> float:
    """The footprint's EXACT board rotation in degrees.

    ``Component.initial_rotation`` is quantized to a 0-3 quadrant index by
    ``io/_parse_modules.py``, which silently loses any non-multiple-of-90
    angle. That parser now also records the raw angle in
    ``attributes["_rotation_deg"]``; this reads it and falls back to the
    quadrant index (with the quantization made explicit) only for
    Components built by something other than the KiCad parser.
    """
    raw = comp.attributes.get("_rotation_deg") if comp.attributes else None
    if raw is not None:
        return float(raw)
    return float((comp.initial_rotation or 0) * 90)


def _pads_for_component(comp: Any) -> list[dict[str, Any]]:
    """Serialize a parsed ``Component``'s pins into the validator's pad schema.

    ``Pin.position`` is the pad's offset from the footprint's pad-bounding-box
    centre in the footprint's UNROTATED frame, and ``Component.initial_position``
    is that centre in board coordinates, so the validator's
    ``world = position + R(theta) * offset`` reconstructs the pad's true board
    position exactly (see ``clearance._rotate`` for the sign convention and why
    it must match this repo's parser).
    """
    pads: list[dict[str, Any]] = []
    for pin in comp.pins:
        pads.append(
            {
                "number": pin.number or pin.name,
                "net": pin.net,
                "offset": pin.position,
                "width": pin.width,
                "height": pin.height,
                "shape": pin.shape,
                "roundrect_ratio": pin.roundrect_ratio,
                "pad_rotation_deg": pin.pad_rotation_deg,
                "layer": pin.layer,
            }
        )
    return pads


def _copper_reach_mm(pads: list[dict[str, Any]], rotation_deg: float) -> float:
    """How far this component's copper extends from its own origin.

    ``max over pads of (|rotated offset| + pad bounding radius)``. Rotation
    does not change ``|offset|`` and ``pad_bounding_radius`` is provably
    rotation-invariant (see ``core.pad_geometry``), so this figure is
    rotation-independent -- ``rotation_deg`` is accepted only to make that
    explicit at the call site. Used by the HV-proximity check below to turn
    an origin-to-origin distance into a sound lower bound on copper-to-copper
    separation.
    """
    del rotation_deg  # provably irrelevant; see docstring
    from temper_placer.core.pad_geometry import shape_code

    import temper_geometry as _tg

    # Wave 4: delegates to temper_geometry. The kernel replicates CPython's
    # builtin `max()` -- first NaN wins and nothing displaces it -- rather than
    # `f64::max`, which discards NaN and would understate the reach of a
    # component with an unparseable pad offset.
    return _tg.copper_reach_mm_py(
        [
            (
                p["offset"][0],
                p["offset"][1],
                p["width"],
                p["height"],
                shape_code(p["shape"]),
                p["roundrect_ratio"],
            )
            for p in pads
        ]
    )


def _board_surface_geometry(pcb_path: Path) -> dict[str, Any]:
    """Board outline + any interior cutouts, from the real ``Edge.Cuts`` layer.

    The validator only needs to know whether the insulating surface is
    unbroken: with no cutout the surface geodesic between two coplanar points
    IS the straight line, so creepage is exactly the clearance figure; with a
    cutout it is strictly longer and the checker must say so rather than
    silently report clearance as creepage (see
    ``clearance.check_creepage_path``).

    Rings are recovered from the graphic items on ``Edge.Cuts``. Polygons and
    rectangles are rings directly; loose lines/arcs are conservatively treated
    as one ring each **only** for counting purposes. Anything this function
    cannot interpret is reported as a cutout, so an unrecognized outline makes
    the creepage model MORE conservative and louder, never less.
    """
    from kiutils.board import Board as KiBoard

    ki_board = KiBoard.from_file(str(pcb_path))
    items = [g for g in ki_board.graphicItems if getattr(g, "layer", None) == "Edge.Cuts"]

    rings: list[list[tuple[float, float]]] = []
    unrecognized = 0
    for item in items:
        coords = getattr(item, "coordinates", None)
        if coords:
            rings.append([(float(p.X), float(p.Y)) for p in coords])
            continue
        start, end = getattr(item, "start", None), getattr(item, "end", None)
        if start is not None and end is not None and type(item).__name__ in ("GrRect",):
            x0, y0, x1, y1 = float(start.X), float(start.Y), float(end.X), float(end.Y)
            rings.append([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
            continue
        unrecognized += 1

    # Largest-area ring is the board outline; every other ring is a cutout.
    def _area(ring: list[tuple[float, float]]) -> float:
        n = len(ring)
        return (
            abs(
                sum(
                    ring[i][0] * ring[(i + 1) % n][1] - ring[(i + 1) % n][0] * ring[i][1]
                    for i in range(n)
                )
            )
            / 2.0
        )

    outline: list[tuple[float, float]] = []
    cutouts: list[list[tuple[float, float]]] = []
    if rings:
        rings_sorted = sorted(rings, key=_area, reverse=True)
        outline = rings_sorted[0]
        # An Edge.Cuts item this function could not turn into a ring means the
        # outline is more complex than the rings it did recover. Treat every
        # recovered ring as a potential cutout in that case, so the creepage
        # model takes its conservative, loud branch rather than concluding the
        # insulating surface is unbroken.
        cutouts = rings_sorted[1:] if unrecognized == 0 else rings_sorted
    elif unrecognized:
        # No ring recoverable at all: the outline is entirely uninterpretable.
        # One empty marker ring forces the conservative creepage branch.
        cutouts = [[]]

    return {
        "outline": outline,
        "surface_cutouts": cutouts,
        "edge_cuts_items": len(items),
        "edge_cuts_unrecognized": unrecognized,
    }


def load_real_board_placement(
    pcb_path: Path,
    manifest_path: Path,
    netlist_path: Path,
) -> tuple[dict[str, Any], dict[str, VoltageDomain], dict[str, Any]]:
    """Build a (placement, voltage_domains, stats) tuple from the real board.

    Args:
        pcb_path: the ``.kicad_pcb`` board file (positions, pad geometry,
            rotations, board outline).
        manifest_path: ``elec/domain_manifest.yaml`` (the domain
            classification authority).
        netlist_path: the compiled design netlist (``elec/build/default.net``,
            produced by ``make netlist``) -- the net->ref connectivity.

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
            Callers should ``pytest.skip`` on this (tests) or log-and-skip
            (the CLI optimize path), not treat it as a passing or failing
            check.
    """
    pcb_path = Path(pcb_path)
    manifest_path = Path(manifest_path)
    netlist_path = Path(netlist_path)
    if not pcb_path.is_file():
        raise RealBoardUnavailable(f"PCB not found: {pcb_path}")
    if not netlist_path.is_file():
        raise RealBoardUnavailable(
            f"Netlist not found: {netlist_path} -- run `make netlist` first."
        )
    if not manifest_path.is_file():
        raise RealBoardUnavailable(f"Domain manifest not found: {manifest_path}")

    # Intentionally NOT swallowed: a manifest/netlist that fails to parse (or
    # a declared net that no longer exists in the compiled netlist) means the
    # manifest and the compiled design have drifted apart -- a real defect
    # that must fail loudly, not be skipped (which would look identical to
    # "everything is fine, nothing to check").
    netlist = parse_design_netlist(netlist_path)
    domains, chains = _load_manifest(manifest_path)

    net_domains_full: dict[str, VoltageDomain] = {}
    for domain_name, net_names in domains.items():
        for n in net_names:
            if n in netlist.nets:  # net exists in this compiled build
                net_domains_full[n] = _domain_for_manifest_domain(domain_name, n)

    all_net_to_refs = _net_to_refs(netlist)
    pcb_result = parse_kicad_pcb(pcb_path)
    ref_to_position = {
        c.ref: c.initial_position
        for c in pcb_result.netlist.components
        if c.initial_position is not None
    }
    ref_to_pads = {
        c.ref: _pads_for_component(c)
        for c in pcb_result.netlist.components
        if c.initial_position is not None
    }
    ref_to_rotation_deg = {
        c.ref: _rotation_deg_for_component(c)
        for c in pcb_result.netlist.components
        if c.initial_position is not None
    }
    board_geometry = _board_surface_geometry(Path(pcb_path))
    ref_to_copper_reach = {
        ref: _copper_reach_mm(ref_to_pads[ref], ref_to_rotation_deg[ref]) for ref in ref_to_pads
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
            components.append(
                {
                    "ref": ref,
                    "position": position,
                    "nets": nets,
                    # Real pad copper + the footprint's exact board rotation.
                    # Without these the validator falls back to the optimistic
                    # origin-to-origin proxy (and says so, loudly).
                    "rotation_deg": ref_to_rotation_deg[ref],
                    "pads": ref_to_pads[ref],
                }
            )

        nets_dict = {name: {"domain": d} for name, d in classified_nets_present.items()}
        return (
            {"components": components, "nets": nets_dict, "board": board_geometry},
            dict(classified_nets_present),
            ref_to_domain_nets,
            matched,
        )

    # ``placement``/``voltage_domains`` (the tuple this function returns) use
    # the FULL manifest declaration -- see module docstring for why the
    # pre-promotion legacy subset no longer exists (it became identical to the
    # full set when the board was re-placed against all declared nets).
    placement, voltage_domains, ref_to_domain_nets, matched_refs = _build_placement(
        net_domains_full
    )

    # --- Coverage + unclassified-component HV-proximity data (FULL set) ---
    all_refs_with_pos = set(ref_to_position)
    classified_refs = {c["ref"] for c in placement["components"]}
    unclassified_refs = sorted(all_refs_with_pos - classified_refs)

    ref_to_instance_path = {
        comp.ref: comp.instance_path
        for comp in netlist.components
    }
    ref_to_all_nets: dict[str, list[str]] = {}
    for net_name, refs in all_net_to_refs.items():
        for ref in refs:
            ref_to_all_nets.setdefault(ref, []).append(net_name)

    hv_refs_with_pos = sorted(
        ref
        for ref in classified_refs
        if ref in ref_to_position
        and any(
            net_domains_full.get(n) in _HV_DOMAINS for n in ref_to_domain_nets.get(ref, [])
        )
    )

    exempt_pairs = _chain_sibling_exempt_pairs(netlist, chains)

    # Copper-aware, like the validator itself. This check carried exactly the
    # same defect the validator did: it ranked "nearest HV part" by
    # origin-to-origin distance and compared THAT to an IEC margin. Copper
    # extends outward from an origin, so that figure is an upper bound on true
    # separation -- optimistic, in the unsafe direction. It now measures real
    # copper, through the validator's own ``_CopperModel`` rather than a second
    # geometry implementation. Passing an empty net-domain map makes
    # ``pads_in_domain`` fall back to every pad of each component, which is what
    # this check wants: an unclassified component has no domain, so all of its
    # copper counts.
    proximity_model = _CopperModel(
        {
            "components": [
                {
                    "ref": ref,
                    "position": ref_to_position[ref],
                    "rotation_deg": ref_to_rotation_deg[ref],
                    "pads": ref_to_pads[ref],
                    "nets": [],
                }
                for ref in ref_to_position
            ]
        }
    )
    _ANY = VoltageDomain.ISOLATED  # unused as a domain; see comment above

    proximity_findings: list[dict[str, Any]] = []
    for ref in unclassified_refs:
        pos = ref_to_position[ref]
        best_dist: float | None = None
        best_ref: str | None = None
        best_origin_dist: float = math.inf
        for href in hv_refs_with_pos:
            if href == ref:
                continue
            # Cheap sound prefilter first: if even the lower bound cannot beat
            # the incumbent, the exact measurement cannot either.
            if best_dist is not None and proximity_model.lower_bound(ref, href) >= best_dist:
                continue
            d, _model, _label = proximity_model.copper_distance(ref, _ANY, href, _ANY, {})
            if best_dist is None or d < best_dist:
                best_dist = d
                best_ref = href
                best_origin_dist = math.dist(pos, ref_to_position[href])
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
                # EXACT copper-to-copper separation (see comment above). The
                # origin-to-origin figure this used to report is kept alongside
                # so the difference is visible rather than silently swapped.
                "distance_mm": best_dist,
                "origin_distance_mm": best_origin_dist,
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

    declared_nets_total = sum(len(v) for v in domains.values())
    total_components = len(all_refs_with_pos)

    stats = {
        "pcb_components": len(ref_to_position),
        "netlist_components": len(netlist.components),
        "netlist_refs_on_classified_nets": len(ref_to_domain_nets),
        "matched_components_in_placement": matched_refs,
        "classified_nets_present": sorted(voltage_domains),
        "classified_nets_requested_but_absent": sorted(
            set(net_domains_full) - set(voltage_domains)
        ),
        # --- Full-manifest-derived numbers (the honest, whole-board
        # picture; see module docstring) ---
        # Separate copies (not aliases of the returned placement/domains):
        # the pre-hoist fixture built these from a second _build_placement
        # pass, and a stats consumer mutating them must not move the
        # placement the validator is actually asserted against.
        "full_placement": copy.deepcopy(placement),
        "full_voltage_domains": copy.deepcopy(voltage_domains),
        "matched_components_in_placement_full": matched_refs,
        "classified_nets_present_full": sorted(voltage_domains),
        "declared_nets_total": declared_nets_total,
        "compiled_nets_total": len(netlist.nets),
        "unclassified_nets_total": len(netlist.nets) - len(voltage_domains),
        "total_components": total_components,
        "unclassified_components": unclassified_refs,
        "unclassified_components_count": len(unclassified_refs),
        "coverage_ratio": (matched_refs / total_components) if total_components else 0.0,
        "max_iec_margin_mm": MAX_IEC_MARGIN_MM,
        # Protective-impedance chain sibling pairs exempted from the proximity
        # check (see _chain_sibling_exempt_pairs) -- exposed so a downstream
        # clearance-repair solve can mirror the exemption exactly instead of
        # over-constraining chain siblings (issue #504 machinery).
        "chain_sibling_exempt_pairs": exempt_pairs,
        # Every unclassified component's distance to its nearest
        # HV-classified neighbour, sorted closest-first, regardless of
        # distance -- the caller (test_temper_board_clearance_compliance)
        # is the one that decides which of these count as a hard failure
        # (distance_mm < max_iec_margin_mm and not exempt), so the margin
        # itself lives in one place, not duplicated here.
        "proximity_findings": proximity_findings,
        # --- Copper geometry (added with the copper-to-copper clearance fix) ---
        # Every component now carries real pad geometry, so a fallback to the
        # optimistic origin-to-origin proxy anywhere is a defect, not a
        # tolerable simplification -- asserted in
        # test_temper_board_clearance_compliance rather than merely reported.
        "components_without_pads": sorted(ref for ref, pads in ref_to_pads.items() if not pads),
        "board_geometry": board_geometry,
        "board_cutout_count": len(board_geometry["surface_cutouts"]),
        "max_copper_reach_mm": max(ref_to_copper_reach.values(), default=0.0),
    }
    return placement, voltage_domains, stats


__all__ = [
    "MAX_IEC_MARGIN_MM",
    "RealBoardUnavailable",
    "load_real_board_placement",
]
