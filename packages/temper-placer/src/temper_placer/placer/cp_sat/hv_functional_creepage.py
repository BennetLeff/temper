"""HV<->HV **functional** creepage for CP-SAT placement, derived per pairing.

THE GAP THIS CLOSES. ``isolation_barrier.py`` separates the HV domain from
the SELV domain and says, in its own words, *"HV<->HV functional pairings
(e.g. DC_BUS<->TANK, floor 10.0 mm) live entirely on the barrier's HV side
and this family says nothing about them"*. Nothing else priced them either:
``IECCreepageGate`` filters only violations that cross the HV<->SELV
boundary, and ``pair_creepage.generated.yaml`` charges HV-class against
HV-class **0.0 mm**. So the placer could pack the HV pocket arbitrarily
tightly at zero cost -- and did: the compliant model-E placement introduced
new sub-2 mm HV<->HV pairs precisely because the model did not price them
(``docs/evidence/2026-08-20-ovp-pads-under-model-e-placement.md``).

``tank_creepage.py`` is the one partial exception: it posts a
``SeparatedConstraint`` between the tank part and every other
``HighVoltage``-class component at the **literal** ``HV_TANK_CREEPAGE_PD3_MM
= 10.0``. That figure happens to coincide with what this module derives for
``*<->TANK`` (Table 18, ``>500-800``), but it is written, not derived, it is
keyed on a *net class* rather than on a declared insulation group, and it
carries no indeterminacy flag -- so a caller can read a SAT verdict off it
and report "pass" for a 47 kHz pairing whose requirement nobody has read.
This module derives the figure and carries the flag; it does not touch
``tank_creepage.py``.

THE DERIVATION -- NO MILLIMETRE IS WRITTEN HERE
------------------------------------------------
Every figure comes from the same chain the barrier family already uses::

    elec/insulation_manifest.yaml     groups + frequencies + each PAIRING's
                                      long-term r.m.s. working voltage
      -> insulation.rs                same-domain -> FUNCTIONAL (cl. 3.3.5)
      -> voltage_range_for(v_rms)     IEC 60664-1 cl. 3.2.1.1
      -> table_18_lookup              Table 18, **UNDOUBLED**
      -> Requirement{Determined | IndeterminateWithFloor}

Cross-domain pairings derive to *reinforced* and are graded against Table 17
**doubled** (cl. 29.2.3). Same-domain pairings do not: cl. 29.2.3's x2 is a
reinforced-insulation provision, so a functional pairing takes its Table 18
figure as printed. That distinction is the whole reason the bus rail-to-rail
crossing is **5.0 mm and not 12.6 mm** -- ``0cbc04248``.

Note for anyone re-reading a row: **Table 18's rows are offset by one from
Table 17's**. ``insulation.rs`` reads each table's own row list, so a row is
never selected by index across tables; a reader checking this module's output
should compare the printed ``voltage_range`` against the printed table name,
not against a row number remembered from the other table.

As declared today (``hv_functional_separations()`` prints exactly this)::

    MAINS<->MAINS          120.0 V  Table 18   >50-125    2.20 mm  determinate
    DC_BUS<->DC_BUS        340.0 V  Table 18  >250-400    5.00 mm  determinate
    DC_BUS<->MAINS         340.0 V  Table 18  >250-400    5.00 mm  determinate
    DC_BUS<->SWITCHING     340.0 V  Table 18  >250-400    5.00 mm  FLOOR ONLY
    MAINS<->SWITCHING      340.0 V  Table 18  >250-400    5.00 mm  FLOOR ONLY
    SWITCHING<->SWITCHING  340.0 V  Table 18  >250-400    5.00 mm  FLOOR ONLY
    DC_BUS<->TANK          570.5 V  Table 18  >500-800   10.00 mm  FLOOR ONLY
    MAINS<->TANK           570.5 V  Table 18  >500-800   10.00 mm  FLOOR ONLY
    SWITCHING<->TANK       570.5 V  Table 18  >500-800   10.00 mm  FLOOR ONLY
    TANK<->TANK            570.5 V  Table 18  >500-800   10.00 mm  FLOOR ONLY

SEVEN OF THE TEN ARE NOT DETERMINATE 5.0 / 10.0 mm
---------------------------------------------------
``SWITCHING`` and ``TANK`` carry 47 kHz. A pairing's frequency is the **max**
of its two groups' (``insulation.rs``: ``fa.frequency_hz.max(fb.frequency_hz)``),
so any HV<->HV pairing touching either group is above IEC 60664-1 cl. 1.1.1's
30 kHz scope ceiling, and cl. 2.3 routes dimensioning above it to
IEC 60664-4 -- paywalled, not obtained. For those seven the resolver answers
``requirement_mm() -> nan`` and ``grade(x) -> "INDETERMINATE"`` at any
distance, never ``"PASS"``.

Getting this wrong in the *permissive* direction -- calling a 47 kHz HV<->HV
pair a determinate 5.0 mm because Table 18 happens to have a row at 340 V --
is the failure mode this module exists to avoid. CP-SAT takes a number, so
the constraint below encodes the **proven floor**; ``determinable`` travels
with every separation and with the report, and a caller that reports a
verdict must check it. A SAT solve here certifies the floor was cleared. It
never certifies compliance.

WHAT THIS FAMILY CANNOT FIX, AND SAYS SO
-----------------------------------------
Two pads of the *same* footprint move as one rigid unit, so no placement,
rotation or corridor changes the distance between them -- the identical
limitation ``tank_creepage.py`` and ``domain_clearance.py`` already record,
and the reason T1 and T2 are the barrier's UNSAT core. HV<->HV has its own
population of these: ``R30.1``/``R30.2`` at 5.000 mm against a 10.0 mm
``TANK<->TANK`` floor, and the 0.650-2.950 mm pairs inside ``C22``, ``C23``,
``D4``, ``R18``-``R23``, ``U4``-``U7``. :func:`intra_package_shortfalls`
enumerates them at exact Minkowski copper distance; they are reported, never
encoded, and never absorbed into a threshold.

**One reported member is an artefact, and it is reported anyway.**
``K1.13``/``K1.14`` come out at **0.000 mm** against a determinate 2.20 mm
``MAINS<->MAINS`` figure -- but the board declares both pads
``(layers "F.Fab")``, a fabrication *documentation* layer that places no
copper, while ``Pin.layer`` reports ``"F.Cu"`` for them. They are the only
two such pads on this board (2 of 527). This function has no view of the raw
``(layers ...)`` token -- it sees only the parsed ``Pin`` -- so it
over-reports rather than guessing, which is the safe direction for a
function whose output is a report and never a constraint. The parser
mis-assignment is a defect of ``parse_kicad_pcb``, is inherited by every
copper-distance census in this repo that reads pad layers through it, and is
recorded here rather than worked around silently.
``docs/evidence/2026-08-20-hv-hv-functional-census.py::non_copper_pads``
filters them out of the measured counts and names them while doing so.

UNDECLARED NETS RAISE, THEY DO NOT DEFAULT
-------------------------------------------
Four ``safety.ovp.*`` nets are ``HighVoltage`` in ``TEMPER_NET_ASSIGNMENTS``
but absent from ``elec/insulation_manifest.yaml``. ``requirement_for_nets``
raises against every counterparty and **no figure exists for them** -- not
5.0, not 2.2, not 0.0. :func:`undeclared_hv_nets` names them so the
declaration gap stays visible; this module never invents a figure to cover
one, and never treats an undeclared net as "no constraint".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import temper_placer.core.insulation_coordination as _insulation

if TYPE_CHECKING:
    from temper_placer.core.netlist import Netlist
    from temper_placer.placer.cp_sat.model import CpSatModel

logger = logging.getLogger(__name__)

__all__ = [
    "ComponentPairRequirement",
    "FunctionalSeparation",
    "HvFunctionalReport",
    "IntraPackageShortfall",
    "add_hv_functional_creepage_to_model",
    "component_hv_nets",
    "generate_hv_functional_constraints",
    "hv_functional_separations",
    "intra_package_shortfalls",
    "undeclared_hv_nets",
]


@dataclass(frozen=True)
class FunctionalSeparation:
    """One declared same-domain HV pairing, resolved.

    ``floor_mm`` is the Table 18 figure at the pairing's declared working
    voltage. When ``determinable`` is ``False`` it is a **proven lower
    bound** from the <=30 kHz tables and clearing it is not compliance.
    """

    pairing_key: str
    group_a: str
    group_b: str
    working_voltage_vrms: float
    table: str
    voltage_range: str
    floor_mm: float
    determinable: bool

    @property
    def requirement_mm(self) -> float:
        """The requirement, or ``nan`` when it is not determinable."""
        return self.floor_mm if self.determinable else float("nan")


def hv_functional_separations() -> dict[str, FunctionalSeparation]:
    """Every declared **same-domain HV** pairing, keyed by pairing key.

    Same-domain because those are the pairings that derive to functional
    insulation (cl. 3.3.5); HV because SELV<->SELV, while equally functional,
    is not what crowds the HV pocket and has no placer consumer. Both halves
    are read off the resolved pairing (``domain_a``/``domain_b``,
    ``crosses_barrier``), never re-parsed from the YAML.

    Raises ``ValueError`` if the declaration carries no same-domain HV
    pairing at all -- an empty family would silently encode nothing, which is
    exactly the 0.0 mm state this module replaces.
    """
    out: dict[str, FunctionalSeparation] = {}
    for pairing in _insulation._resolution().pairings():
        if pairing.crosses_barrier():
            continue
        if pairing.domain_a() != "HV" or pairing.domain_b() != "HV":
            continue
        out[pairing.key()] = FunctionalSeparation(
            pairing_key=pairing.key(),
            group_a=pairing.group_a(),
            group_b=pairing.group_b(),
            working_voltage_vrms=float(pairing.working_voltage_vrms()),
            table=pairing.table(),
            voltage_range=pairing.voltage_range(),
            floor_mm=float(pairing.enforceable_floor_mm()),
            determinable=bool(pairing.is_determinable()),
        )
    if not out:
        raise ValueError(
            "no same-domain HV pairing is declared in elec/insulation_manifest.yaml -- "
            "refusing to encode an HV<->HV family with no derived requirement "
            "(anti-vacuity). Every unordered pair of declared groups, including "
            "self-pairs, must carry an entry."
        )
    return out


def component_hv_nets(netlist: Netlist) -> dict[str, list[str]]:
    """``ref -> sorted declared-HV nets`` for every component carrying one.

    Membership comes from the insulation declaration
    (``net_domain(net) == "HV"``), which is net-exact and proved against
    ``elec/domain_manifest.yaml`` by ``scripts/check_insulation_pairings.py``
    -- never from a name pattern, and never from a net class (a net class is
    a coarser partition that mixes 120 V mains with the 570.5 V tank).
    """
    out: dict[str, list[str]] = {}
    for comp in netlist.components:
        nets = sorted(
            {p.net for p in comp.pins if p.net and _insulation.net_domain(p.net) == "HV"}
        )
        if nets:
            out[comp.ref] = nets
    return out


def undeclared_hv_nets(netlist: Netlist, net_to_class: dict[str, str]) -> dict[str, list[str]]:
    """Nets this repo's net-class tables call HighVoltage-family that the
    insulation declaration does not carry: ``net -> sorted refs``.

    Reported, never defaulted. ``requirement_for_nets`` raises for these, and
    that is the fail-closed direction: an undeclared net has no requirement
    and none may be assumed. Handing one the family's smallest figure -- or
    its largest -- would both be inventing a safety number.
    """
    family = {
        "ACMains",
        "GateDriveHV",
        "HighVoltage",
        "HighVoltageIsolated",
        "HighVoltageSignal",
        "HighVoltageTank",
    }
    out: dict[str, set[str]] = {}
    for comp in netlist.components:
        for pin in comp.pins:
            if not pin.net or _insulation.net_domain(pin.net) is not None:
                continue
            if net_to_class.get(pin.net) in family:
                out.setdefault(pin.net, set()).add(comp.ref)
    return {net: sorted(refs) for net, refs in sorted(out.items())}


@dataclass(frozen=True)
class ComponentPairRequirement:
    """The functional figure two components owe each other, and its status."""

    ref_a: str
    ref_b: str
    floor_mm: float
    determinable: bool
    governing_pairing: str
    governing_nets: tuple[str, str]

    @property
    def requirement_mm(self) -> float:
        return self.floor_mm if self.determinable else float("nan")


def _pair_requirement(
    ref_a: str, nets_a: list[str], ref_b: str, nets_b: list[str]
) -> ComponentPairRequirement | None:
    """The worst declared HV<->HV pairing over two components' HV nets.

    ``max`` over floors and ``all`` over determinability -- the same
    conservatism ``insulation_coordination.requirement_for_net_classes`` and
    ``isolation_barrier.barrier_setbacks`` use, and for the same reason: a
    single geometric constraint between two whole bounding boxes must be
    sized by the worst pad pair it stands in for, and an indeterminacy cannot
    be diluted by pairing it with determinable neighbours.

    Identical nets contribute nothing: two pads at the same potential have no
    insulation between them to dimension.
    """
    best = float("-inf")
    determinable = True
    governing = ""
    governing_nets = ("", "")
    for na in nets_a:
        for nb in nets_b:
            if na == nb:
                continue
            pairing = _insulation.requirement_for_nets(na, nb)
            determinable = determinable and pairing.is_determinable()
            floor = float(pairing.enforceable_floor_mm())
            if floor > best:
                best = floor
                governing = pairing.key()
                governing_nets = (na, nb)
    if governing == "":
        return None
    return ComponentPairRequirement(
        ref_a=ref_a,
        ref_b=ref_b,
        floor_mm=best,
        determinable=determinable,
        governing_pairing=governing,
        governing_nets=governing_nets,
    )


@dataclass(frozen=True)
class IntraPackageShortfall:
    """Two pads of ONE footprint that are closer than their own figure.

    Placement-invariant: a footprint's pads move as one rigid unit, so this
    shortfall survives every position, rotation and corridor the solver can
    choose. Reported so it is visible; never encoded, and never absorbed.
    """

    ref: str
    pad_a: str
    pad_b: str
    net_a: str
    net_b: str
    gap_mm: float
    floor_mm: float
    determinable: bool
    governing_pairing: str

    @property
    def short_by_mm(self) -> float:
        return self.floor_mm - self.gap_mm


def intra_package_shortfalls(netlist: Netlist) -> list[IntraPackageShortfall]:
    """Every within-footprint HV<->HV pad pair below its own figure.

    Exact Minkowski copper-to-copper (``core.pad_geometry.pad_pair_distance``)
    through the settled pad-world composition
    (``temper_placer.geometry.pad_world`` -- ``world_centre = (FX,FY) +
    R(-THETA).(LX,LY)``, ``world_body_angle = comp_rotation_deg +
    pad_rotation_deg``), so the figure is the copper's, not a bounding box's.
    Placement-invariant, so measuring it at the committed coordinates
    measures it at every coordinate.
    """
    from temper_placer.core.pad_geometry import pad_pair_distance
    from temper_placer.geometry.pad_world import pin_pair_spec

    out: list[IntraPackageShortfall] = []
    for comp in netlist.components:
        pins = [
            p for p in comp.pins if p.net and _insulation.net_domain(p.net) == "HV"
        ]
        if len(pins) < 2:
            continue
        cx, cy = comp.initial_position or (0.0, 0.0)
        rot_deg = float(comp.initial_rotation_quadrant) * 90.0
        specs = [pin_pair_spec(p, cx, cy, rot_deg) for p in pins]
        for i in range(len(pins)):
            for j in range(i + 1, len(pins)):
                if pins[i].net == pins[j].net:
                    continue
                pairing = _insulation.requirement_for_nets(pins[i].net, pins[j].net)
                gap = pad_pair_distance(specs[i], specs[j])
                floor = float(pairing.enforceable_floor_mm())
                if gap >= floor:
                    continue
                out.append(
                    IntraPackageShortfall(
                        ref=comp.ref,
                        pad_a=str(pins[i].number),
                        pad_b=str(pins[j].number),
                        net_a=pins[i].net,
                        net_b=pins[j].net,
                        gap_mm=gap,
                        floor_mm=floor,
                        determinable=bool(pairing.is_determinable()),
                        governing_pairing=pairing.key(),
                    )
                )
    return sorted(out, key=lambda s: (s.gap_mm, s.ref, s.pad_a, s.pad_b))


@dataclass(frozen=True)
class HvFunctionalReport:
    """What the family derived, encoded, and could not encode."""

    separations: dict[str, FunctionalSeparation]
    pair_requirements: tuple[ComponentPairRequirement, ...]
    intra_package: tuple[IntraPackageShortfall, ...]
    undeclared: dict[str, list[str]]

    @property
    def determinable(self) -> bool:
        """``False`` while ANY encoded figure is a proven lower bound.

        It is ``False`` on this board: seven of the ten HV<->HV pairings run at
        47 kHz. While it is ``False``, a SAT verdict from a model containing
        this family certifies that the floors were cleared and nothing more.
        """
        return all(s.determinable for s in self.separations.values())

    @property
    def widest_mm(self) -> float:
        return max(s.floor_mm for s in self.separations.values())


def generate_hv_functional_constraints(netlist: Netlist) -> tuple[list, HvFunctionalReport]:
    """``(SeparatedConstraints, report)`` for every HV<->HV component pair.

    One HARD ``SeparatedConstraint`` per unordered pair of distinct
    components that each carry a declared HV net, at the worst figure their
    own nets earn. No margin argument exists and none is accepted: a
    caller-chosen figure is exactly the untraceable literal this family
    replaces.

    SOUNDNESS. ``SeparatedConstraint`` encodes a Chebyshev gap between two
    bounding boxes, and ``comp.bounds`` is constructed to *contain* every pad
    the component places (``tank_creepage.py`` sec 1 carries the full
    argument, proven by
    ``test_bounds_computed_in_placement_frame_not_raw_anchor``). So a SAT
    bounding-box gap of at least F implies every pad-copper point of A is at
    least F from every pad-copper point of B. The encoding can only
    over-constrain.

    Self-pairs are skipped, because no placement can change them -- see
    :func:`intra_package_shortfalls`, which measures them instead.
    """
    from temper_placer.core.design_rules import create_temper_design_rules
    from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint
    from temper_placer.router_v6.pair_creepage import net_class_of

    separations = hv_functional_separations()
    hv_nets = component_hv_nets(netlist)

    rules = create_temper_design_rules()
    net_to_class = {
        p.net: net_class_of(p.net, rules)
        for c in netlist.components
        for p in c.pins
        if p.net
    }

    refs = sorted(hv_nets)
    requirements: list[ComponentPairRequirement] = []
    constraints = []
    for i, ra in enumerate(refs):
        for rb in refs[i + 1 :]:
            req = _pair_requirement(ra, hv_nets[ra], rb, hv_nets[rb])
            if req is None:
                continue
            requirements.append(req)
            flag = "" if req.determinable else " [PROVEN FLOOR ONLY -- 47 kHz, "
            if flag:
                flag += "IEC 60664-4 not obtained; clearing it is NOT compliance]"
            constraints.append(
                SeparatedConstraint(
                    a=ra,
                    b=rb,
                    min_distance_mm=req.floor_mm,
                    tier=ConstraintTier.HARD,
                    because=(
                        f"IEC 60335-1 functional creepage, derived per pairing: "
                        f"{req.governing_pairing} "
                        f"({req.governing_nets[0]} <-> {req.governing_nets[1]}), "
                        f"{separations[req.governing_pairing].table} row "
                        f"{separations[req.governing_pairing].voltage_range} at "
                        f"{separations[req.governing_pairing].working_voltage_vrms} Vrms "
                        f"= {req.floor_mm}mm undoubled{flag}"
                    ),
                    id=f"hv_functional_{ra}_{rb}",
                )
            )

    report = HvFunctionalReport(
        separations=separations,
        pair_requirements=tuple(requirements),
        intra_package=tuple(intra_package_shortfalls(netlist)),
        undeclared=undeclared_hv_nets(netlist, net_to_class),
    )
    if report.intra_package:
        logger.warning(
            "%d HV<->HV pad pairs are INTRA-PACKAGE and below their own functional "
            "figure -- no placement constraint can fix these: %s",
            len(report.intra_package),
            ", ".join(f"{s.ref}.{s.pad_a}<->{s.ref}.{s.pad_b}" for s in report.intra_package),
        )
    if report.undeclared:
        logger.warning(
            "%d HighVoltage-family nets are UNDECLARED in the insulation manifest, so "
            "NO HV<->HV figure exists for them: %s",
            len(report.undeclared),
            ", ".join(sorted(report.undeclared)),
        )
    return constraints, report


def add_hv_functional_creepage_to_model(
    model: CpSatModel, netlist: Netlist
) -> HvFunctionalReport:
    """Post the family's HARD constraints straight onto *model*.

    Mirrors ``tank_creepage.add_tank_creepage_to_model``: encode each
    ``SeparatedConstraint`` through the registered handler with ``ctx=None``
    (every ``a``/``b`` here is a literal ref already in ``components``, so
    ``handlers/_shared.resolve_refs`` returns before it touches ``ctx``).
    """
    from temper_placer.placer.cp_sat.handlers.separated import encode_separated

    constraints, report = generate_hv_functional_constraints(netlist)
    components = model.component_map
    for constraint in constraints:
        if constraint.a not in components or constraint.b not in components:
            continue
        encode_separated(constraint, components, model, None)  # type: ignore[arg-type]
    logger.info(
        "HV<->HV functional creepage: %d component-pair constraints, widest %.2fmm, "
        "all_determinable=%s",
        len(constraints),
        report.widest_mm,
        report.determinable,
    )
    return report
