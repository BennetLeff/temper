"""Protective-impedance chain co-location: a placement constraint keeping
the members of a declared series resistor chain physically adjacent.

Why this module exists
----------------------
``elec/domain_manifest.yaml`` declares two ``protective_impedance_chains``
-- series strings of three resistors each, split from what would
electrically be a single part so that no single short removes the
impedance (IEC 60335-1 protective impedance; the split itself is recorded
in ``docs/evidence/2026-07-26-ovp-crossing-resolution.md``)::

    ovp01_comparator_divider: safety.ovp.r_div_top1 -> _top2 -> _top3
    ovp01_adc_sense_divider:  safety.ovp.r_adc_top1 -> _top2 -> _top3

The manifest constrains the chain's *existence* (``min_length: 3``, each
member "a genuine two-terminal part ... wired in series to its
neighbour"). **Nothing constrains where the members go.** Measured
directly from ``pcb/temper.kicad_pcb`` (read-only; this module does not
modify the board):

===== ========================= ================== ==================
Ref   instance                  ``(at x y)``       gap to predecessor
===== ========================= ================== ==================
R51   ``r_div_top1``            ``(97.43, 189.19)``  --
R52   ``r_div_top2``            ``(168.79, 170.63)`` **73.7mm**
R53   ``r_div_top3``            ``(84.41, 242.27)``  **110.7mm**
R56   ``r_adc_top1``            ``(33.23, 97.29)``   --
R57   ``r_adc_top2``            ``(167.82, 174.44)`` **155.1mm**
R58   ``r_adc_top3``            ``(114.35, 138.76)`` **64.3mm**
===== ========================= ================== ==================

on a 180 x 260mm board. Both chains are scattered across essentially the
whole board.

Why that is a routing problem, not just untidy
-----------------------------------------------
A chain's **interior nodes** -- the nets joining member *i* to member
*i+1* -- are pure artifacts of the split. They carry no signal anywhere;
each is a two-pad net whose only job is to connect one resistor's ``p2``
to the next one's ``p1``. Placed adjacent they are millimetre stubs.
Placed 74mm and 111mm apart they become the two longest Default-class
traces on the board -- and, because both interior nodes of one chain
terminate on **opposite pads of the same middle resistor**, they leave
that resistor in the same direction and traverse the board *together*.

That is the mechanism behind the ``x[40,60)`` clearance band measured in
``docs/evidence/2026-08-12-clearance-congestion-band.md`` (retired to
history by the #1100 revert, re-derived here in
``docs/evidence/2026-08-12-ovp-divider-parallel-bus.md``):
``safety.ovp.r_div_top1-p2`` x ``safety.ovp.r_div_top2-p2`` -- precisely
the comparator chain's two interior nodes -- account for 121 clearance
violations *between those two nets alone*. They are not two unrelated
nets that happened to converge. They are the two ends of R52.

The interior nodes are also, per ``domain_manifest.yaml``'s own comment
(~line 347), **deliberately unclassified** -- "genuinely mid-chain,
neither HV nor SELV by voltage". So they fall to the ``Default``
netclass, which is why 205 of 205 band violations fire the one rule
``"Default routing"`` at 0.2mm rather than any netclass-specific rule.

Why no new constraint type
--------------------------
The only wire type emitted here is ``adjacent``, already registered in
both backends -- Pumpkin ``docs/evidence/2026-08-07-pumpkin-engine/src/main.rs:358``,
OR-Tools ``handlers/adjacent.py:22``. This follows
``heatsink_colocation.py``'s reasoning verbatim: Pumpkin ``exit(2)``s on
an unregistered type while OR-Tools warns and continues, so a new type
encoded in one backend under-constrains the other silently. It also
means the pinned engine binary (``scripts/verify_pumpkin_engine.py``)
does not have to be rebuilt and re-pinned.

Unlike the heatsink group, this constraint needs **no rotation pin**: a
series chain has no shared mechanical face, so there is no orientation
requirement to express. That is the reason this module is much smaller
than ``heatsink_colocation.py`` despite following its shape.

Chain membership is derived, not transcribed
---------------------------------------------
Board designators are **not** hard-coded. The manifest names atopile
instance paths (``safety.ovp.r_div_top1``); the board names nets. The two
meet at the interior node's net name, which atopile emits as
``f"{instance}-p2"`` -- so the net ``safety.ovp.r_div_top1-p2`` is
exactly the node joining ``r_div_top1.p2`` to ``r_div_top2.p1``, and the
two components carrying a pad on it are exactly the consecutive pair to
co-locate. :func:`resolve_chain_pairs` does that lookup against the
parsed netlist, so a refdes reshuffle cannot silently decouple this
constraint from the parts it means (the failure mode
``heatsink_colocation.py`` documents for ``Q1``/``Q2``).

Verified against the committed board: the derivation recovers
``(R51, R52)``, ``(R52, R53)``, ``(R56, R57)``, ``(R57, R58)`` -- four
pairs, matching the manifest's two chains of three.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.model import CpSatModel

__all__ = [
    "MAX_CHAIN_GAP_MM",
    "ChainPair",
    "ChainViolation",
    "check_chain_colocation",
    "chain_colocation_wire_constraints",
    "add_chain_colocation_to_model",
    "load_protective_impedance_chains",
    "resolve_chain_pairs",
]


#: Maximum permitted edge-to-edge gap between consecutive chain members, mm.
#:
#: **NOT independently derived -- this is a declaration, and is recorded as
#: one rather than dressed up as physics.** No in-repo document states how
#: close the members of a protective-impedance chain must sit; the
#: manifest constrains the chain's topology (``min_length: 3``) and says
#: nothing about geometry.
#:
#: What bounds it from below: the members are 1206
#: (``Resistor_SMD:R_1206_3216Metric``, 3.2 x 1.6mm body) and the
#: courtyard backfill already separates every component pair by
#: tau = 0.40mm (``courtyard_clearance_mm(0.2)``), so any value below
#: ~0.4mm is unsatisfiable by construction and a value near it leaves no
#: room for the fanout via each interior node needs.
#:
#: What bounds it from above: the constraint's entire purpose is that the
#: interior node stay a *local stub* rather than a board-spanning trace.
#: On a 180 x 260mm board anything in the low tens of millimetres achieves
#: that; the committed board's 73.7 / 110.7 / 155.1mm does not.
#:
#: 10.0mm is ~3 package lengths. It is chosen deliberately **loose** --
#: roughly 25x the courtyard floor -- because the constraint has to
#: compose with the PD2/8.0mm isolation barrier and the shared-heatsink
#: co-location, and a tight bound that tips the model infeasible measures
#: nothing. It still collapses the committed scatter by 7-15x.
#: ``docs/evidence/2026-08-12-ovp-divider-parallel-bus.md`` reports the
#: sensitivity sweep over this figure rather than asserting it is optimal.
MAX_CHAIN_GAP_MM: float = 10.0


@dataclass(frozen=True)
class ChainPair:
    """Two consecutive members of one declared chain, plus the net joining them."""

    chain_name: str
    a: str
    b: str
    interior_net: str


@dataclass(frozen=True)
class ChainViolation:
    """One consecutive pair that a placement puts too far apart."""

    chain_name: str
    refs: tuple[str, str]
    interior_net: str
    measured_mm: float
    limit_mm: float

    @property
    def detail(self) -> str:
        return (
            f"{self.chain_name}: {self.refs[0]}-{self.refs[1]} edge-to-edge gap "
            f"{self.measured_mm:.2f}mm exceeds {self.limit_mm:.2f}mm; interior "
            f"node {self.interior_net} becomes a board-spanning trace"
        )


def load_protective_impedance_chains(manifest_path: Path | str) -> list[dict[str, Any]]:
    """Read ``protective_impedance_chains`` from the domain manifest.

    Returns the raw declarations. The manifest is the SSOT for which parts
    form a chain -- this module never invents membership.
    """
    import yaml

    data = yaml.safe_load(Path(manifest_path).read_text())
    return list(data.get("protective_impedance_chains") or [])


def _interior_net_name(instance_path: str) -> str:
    """Net joining ``instance_path``'s ``p2`` to its successor's ``p1``.

    atopile names a two-terminal part's pin net ``f"{instance}-p2"``;
    confirmed against the committed board, whose net table contains
    ``safety.ovp.r_div_top1-p2`` and ``safety.ovp.r_adc_top1-p2``.
    """
    return f"{instance_path}-p2"


def resolve_chain_pairs(
    chains: Iterable[dict[str, Any]],
    components: Iterable[Any],
) -> list[ChainPair]:
    """Map declared chains onto board designators via their interior nets.

    *components* are parsed netlist components (each with ``.ref`` and
    ``.pins``, each pin carrying ``.net``). For every consecutive pair in
    every chain, the joining net is looked up and the components holding a
    pad on it are returned as the pair to co-locate.

    A pair whose interior net is absent from the board, or which does not
    resolve to exactly two components, is **skipped rather than guessed**
    -- an under-resolved pair would silently constrain the wrong parts.
    """
    net_to_refs: dict[str, set[str]] = {}
    for comp in components:
        for pin in getattr(comp, "pins", ()):
            net = getattr(pin, "net", None)
            if net:
                net_to_refs.setdefault(net, set()).add(comp.ref)

    pairs: list[ChainPair] = []
    for chain in chains:
        name = str(chain.get("name", "<unnamed>"))
        members = list(chain.get("chain") or [])
        for i in range(len(members) - 1):
            net = _interior_net_name(members[i])
            refs = sorted(net_to_refs.get(net, ()))
            if len(refs) != 2:
                continue
            pairs.append(ChainPair(chain_name=name, a=refs[0], b=refs[1], interior_net=net))
    return pairs


def chain_colocation_wire_constraints(
    pairs: Iterable[ChainPair],
    *,
    max_gap_mm: float = MAX_CHAIN_GAP_MM,
    present_refs: frozenset[str] | None = None,
) -> list[dict]:
    """Pumpkin ``ModelSpec.constraints`` entries co-locating each pair.

    Emits only ``adjacent``, which ``main.rs:358-397`` encodes as four
    one-sided edge-to-edge bounds -- an AND across both axes, which is
    what "these two parts sit next to each other" requires.
    """
    out: list[dict] = []
    for p in pairs:
        if present_refs is not None and (p.a not in present_refs or p.b not in present_refs):
            continue
        out.append(
            {
                "type": "adjacent",
                "a": p.a,
                "b": p.b,
                "max_distance_mm": float(max_gap_mm),
                "metric": "edge_to_edge",
                "tier": 1,
                "because": (
                    f"{p.chain_name}: consecutive protective-impedance chain members; "
                    f"interior node {p.interior_net} must stay a local stub, not a "
                    f"board-spanning Default-class trace."
                ),
            }
        )
    return out


def add_chain_colocation_to_model(
    model: CpSatModel,
    pairs: Iterable[ChainPair],
    *,
    max_gap_mm: float = MAX_CHAIN_GAP_MM,
) -> list[str]:
    """Post the same constraints onto an OR-Tools :class:`CpSatModel`.

    Mirrors :func:`chain_colocation_wire_constraints` exactly, using the
    model's own primitives (the approach ``heatsink_colocation`` and
    ``isolation_barrier`` both take). Returns the assumption labels
    created, so an UNSAT core can name this constraint.
    """
    gap_u = model.mm_to_units(max_gap_mm)
    labels: list[str] = []
    for p in pairs:
        try:
            va = model.get_component(p.a)
            vb = model.get_component(p.b)
        except KeyError:
            continue
        label = f"pichain_{p.chain_name}_{p.a}_{p.b}"
        assumption = model.new_assumption(label)
        # Edge-to-edge on both axes, matching main.rs:375-396 and
        # handlers/adjacent.py:62-65.
        model.add_constraint_enforced(va.x_start - vb.x_start - vb.x_size <= gap_u, assumption)
        model.add_constraint_enforced(vb.x_start - va.x_start - va.x_size <= gap_u, assumption)
        model.add_constraint_enforced(va.y_start - vb.y_start - vb.y_size <= gap_u, assumption)
        model.add_constraint_enforced(vb.y_start - va.y_start - va.y_size <= gap_u, assumption)
        labels.append(label)
    return labels


def check_chain_colocation(
    pairs: Iterable[ChainPair],
    positions: dict[str, tuple[float, float]],
    rotations: dict[str, int],
    sizes: dict[str, tuple[float, float]],
    *,
    max_gap_mm: float = MAX_CHAIN_GAP_MM,
) -> list[ChainViolation]:
    """Evaluate the requirement against a concrete placement.

    The solver's predicate run in the other direction: it is what proves
    the committed board violates this constraint, and what proves a solved
    board satisfies it. *positions* are box centres in mm, *sizes* the
    unrotated ``(w0, h0)``.
    """
    out: list[ChainViolation] = []
    for p in pairs:
        if not all(r in positions and r in rotations and r in sizes for r in (p.a, p.b)):
            continue

        def _wh(ref: str) -> tuple[float, float]:
            w0, h0 = sizes[ref]
            return (w0, h0) if rotations[ref] % 2 == 0 else (h0, w0)

        (ax, ay), (bx, by) = positions[p.a], positions[p.b]
        (aw, ah), (bw, bh) = _wh(p.a), _wh(p.b)
        gap_x = max(ax - bx - (aw + bw) / 2.0, bx - ax - (aw + bw) / 2.0)
        gap_y = max(ay - by - (ah + bh) / 2.0, by - ay - (ah + bh) / 2.0)
        gap = max(gap_x, gap_y)
        if gap > max_gap_mm:
            out.append(
                ChainViolation(
                    chain_name=p.chain_name,
                    refs=(p.a, p.b),
                    interior_net=p.interior_net,
                    measured_mm=gap,
                    limit_mm=max_gap_mm,
                )
            )
    return out
