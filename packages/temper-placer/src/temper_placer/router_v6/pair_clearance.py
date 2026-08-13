"""Per-net-PAIR clearance, in the routing DECISION rather than the verdict.

WHAT WAS WRONG
--------------
``OccupancyGrid.mark_path_blocked`` / ``mark_via_blocked`` dilate a
just-routed net's copper by ``trace_width/2 + clearance`` before the *next*
net's A* search runs, and that ``clearance`` comes from
``design_rules.get_rules_for_net(net_name).clearance_mm`` -- the routed net's
OWN net-class figure. Two consequences, both of which produce copper that
violates the board's own safety rules:

1. **The requirement is a property of the pair, and the stamp only knows one
   half of it.** Whichever net routes FIRST decides the separation. A
   SELV/unclassified track routed early is stamped at the 0.2mm default; a
   mains net routed later sees only that 0.2mm halo and is free to run
   0.2mm from it, even though the board requires 6.0mm between them. This is
   order-dependence, not conservatism -- the same pair gets a different
   answer depending on ``_compute_net_order``.

2. **The routing net's own width is never charged.** A* tests the candidate
   path's CENTRELINE against the grid, so the enforced edge-to-edge distance
   is short by the routing net's own ``trace_width/2``.

``ClearanceMatrix.get_clearance`` in ``constraints_design_rules.py`` is a real
per-net-pair table, but every one of its eleven call sites is inside
``constraints_drc_oracle.py`` -- a post-route verification oracle. The
capability was wired to the verification stage, never to the decision stage.
(Re-verified on ``origin/main`` cc732df2b: ``ClearanceMatrix`` is imported by
exactly one non-test module, that oracle.) It could not simply be called from
the A* hot path either: each ``get_clearance`` call re-marshals the whole rule
set across the Rust boundary, and the value it returns still cannot be
expressed in a single occupancy grid -- see below.

WHY ONE GRID CANNOT EXPRESS IT
------------------------------
The occupancy grid is one ``int8`` array per layer whose cells hold the net id
that owns them. For net A already routed and net B searching, the enforced
separation is exactly the stamp radius A was written with. To be pair-correct
that radius would have to be ``w_A/2 + required(A, B) + w_B/2`` -- a function
of B, which is not known when A is stamped. Any single-grid encoding must
therefore pick one radius per A, and the only safe choice is
``max over all B``: on this board that charges every HV net the full 6.0mm
mains bar against its own same-domain neighbours, which the DRU explicitly
relaxes to 0.2-3.0mm. That is the over-broad approximation this module exists
to avoid.

WHAT THIS MODULE DOES INSTEAD
-----------------------------
Groups net classes into *clearance profiles* -- classes that impose the same
requirement on everyone else AND route at the same trace width -- and lets
``profile_grids.ProfileGrids`` keep one occupancy-grid family per profile. Net
B of class ``C`` searches family ``profile(C)``, in which every already-routed
net A was stamped at ``w_A/2 + required(class_A, C) + w_C/2``. That is exact
per class pair, order-independent, and charges both half-widths.

WHERE THE NUMBERS COME FROM
---------------------------
``configs/pair_clearance.generated.yaml``, emitted by
``scripts/generate_kicad_dru.py`` by evaluating the rules it just wrote into
``pcb/temper.kicad_dru`` under KiCad's own last-matching-rule-wins precedence.
That file is what ``kicad-cli pcb drc`` enforces and therefore what the
board's violation count is measured against, so the router is deciding against
the same table it will be judged by -- not a hand-copied restatement of it,
and not ``netclass_rules.yaml``'s ``class_pairs``, whose own comments record
that its 6.0mm HV figures are "legacy, not primary-cited" and that
"the fab-authoritative enforcement point is scripts/generate_kicad_dru.py".
``class_pairs`` also names only 5 of this board's 9 live classes and says
nothing about the 69 of 110 nets that carry no net class at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

# The class KiCad reports for a net with no net-class assignment, and the key
# this module falls back to for any class the generated table does not name.
# Kept in sync with ``generate_kicad_dru.UNASSIGNED_NETCLASS`` by
# ``tests/router_v6/test_pair_clearance.py``.
UNASSIGNED_NETCLASS = "Default"

# ``scripts/generate_kicad_dru.KICAD_NAME_MAP``, in the direction this module
# needs: the router's own class names (from ``netclass_rules.yaml``) into the
# names the generated table is keyed by. A missing entry means the two agree.
_ROUTER_TO_KICAD_CLASS = {"GND": "Ground"}

_DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "pair_clearance.generated.yaml"
)


def kicad_class_name(router_class: str) -> str:
    """Translate a router-side net-class name into the generated table's key."""
    return _ROUTER_TO_KICAD_CLASS.get(router_class, router_class)


@dataclass(frozen=True)
class PairClearanceTable:
    """``{(class_a, class_b): required_mm}``, symmetric and total.

    ``required`` never raises: an unknown class resolves to
    :data:`UNASSIGNED_NETCLASS`, which is the same treatment KiCad gives a net
    with no net-class assignment, and if even that pair is absent it falls
    back to ``default_clearance_mm``. A safety table that raised mid-route
    would turn a missing row into a failed board rather than a conservative
    one.
    """

    pairs: dict[tuple[str, str], float]
    classes: tuple[str, ...]
    default_clearance_mm: float = 0.2

    def required(self, class_a: str, class_b: str) -> float:
        """Required edge-to-edge clearance in mm between two net classes."""
        key_a = kicad_class_name(class_a or UNASSIGNED_NETCLASS)
        key_b = kicad_class_name(class_b or UNASSIGNED_NETCLASS)
        if key_a not in self.classes:
            key_a = UNASSIGNED_NETCLASS
        if key_b not in self.classes:
            key_b = UNASSIGNED_NETCLASS
        value = self.pairs.get((key_a, key_b))
        if value is None:
            value = self.pairs.get((key_b, key_a))
        return self.default_clearance_mm if value is None else value


def load_pair_clearance_table(path: Path | str | None = None) -> PairClearanceTable:
    """Load :data:`_DEFAULT_CONFIG_PATH` (or *path*) into a table."""
    config_path = Path(path) if path is not None else _DEFAULT_CONFIG_PATH
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    classes = tuple(raw["classes"])
    pairs: dict[tuple[str, str], float] = {}
    for key, value in raw["pairs"].items():
        class_a, _, class_b = key.partition("|")
        pairs[(class_a, class_b)] = float(value)
        pairs[(class_b, class_a)] = float(value)
    return PairClearanceTable(pairs=pairs, classes=classes)


@dataclass(frozen=True)
class ClearanceProfiles:
    """Which occupancy-grid family each net class searches.

    Two classes share a profile only when they agree on BOTH halves of what
    the stamp radius depends on: the requirement they impose on every other
    live class, and their own trace width (which the stamp charges as
    ``w_C/2``). Merging on the requirement alone would silently charge a
    0.127mm FinePitch track the 1.0mm Power width.
    """

    profile_of_class: dict[str, str]
    """Router-side class name -> profile key."""

    profile_width_mm: dict[str, float]
    """Profile key -> the trace width its members route at."""

    class_clearance_mm: dict[str, float]
    """Router-side class name -> that class's own ``clearance_mm``."""

    table: PairClearanceTable
    default_class: str = UNASSIGNED_NETCLASS

    @property
    def profiles(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.profile_of_class.values())))

    def profile_for_class(self, net_class: str | None) -> str:
        return self.profile_of_class.get(
            net_class or self.default_class,
            self.profile_of_class[self.default_class],
        )

    def stamp_clearance_mm(self, marked_class: str | None, profile: str) -> float:
        """Clearance to stamp around a *marked_class* net in *profile*'s grid.

        Three terms, and the ``max`` between the first three is what makes
        this change monotone:

        * ``table.required(marked, searching)`` -- the pair figure kicad-cli
          enforces. This is the term that was missing entirely.
        * ``class_clearance_mm[marked]`` -- exactly what the single-grid model
          stamps today. Keeping it as a floor makes the new model provably
          never LOOSER than the old one for any pair, so no same-class
          separation regresses. It matters: the DRU has no ACMains<->ACMains
          *track* rule, so the pair table alone would drop that pair from
          6.0mm to the 0.2mm default.

        Plus the searching profile's own half-width, because A* tests a
        candidate CENTRELINE against the grid. The marked net's own
        ``trace_width/2`` is added by ``mark_path_blocked``'s existing
        ``trace_width`` argument, so it is deliberately not included here.

        NOT included, deliberately: ``class_clearance_mm[searching]`` as a
        second floor. It is symmetric-looking and tempting, but on this board
        it would charge every ``HighVoltageIsolated`` search 6.0mm against
        even a GND track, where the fab-authoritative DRU requires 2.0mm --
        importing ``netclass_rules.yaml``'s own self-described "legacy, not
        primary-cited" figure into the search as if it were the enforced
        requirement, and costing completion for a bar nothing will measure
        against. The floor above is the one that preserves today's behaviour;
        the pair table is the one that supplies the real requirement.
        """
        member = self._representative(profile)
        marked = marked_class or self.default_class
        floor = self.class_clearance_mm.get(marked, 0.0)
        required = max(self.table.required(marked, member), floor)
        return required + self.profile_width_mm[profile] / 2.0

    def _representative(self, profile: str) -> str:
        for net_class, key in self.profile_of_class.items():
            if key == profile:
                return net_class
        raise KeyError(profile)


def resolve_profiles(
    table: PairClearanceTable,
    class_widths: dict[str, float],
    class_clearances: dict[str, float],
    default_width_mm: float,
    default_clearance_mm: float,
) -> ClearanceProfiles:
    """Group the LIVE classes of a board into clearance profiles.

    *class_widths* / *class_clearances* map every net class that actually
    appears on the board to its trace width and own clearance, both in mm.
    ``Default`` is always included -- on this board it is the single largest
    population (69 of 110 nets).
    """
    widths = dict(class_widths)
    widths.setdefault(UNASSIGNED_NETCLASS, default_width_mm)
    clearances = dict(class_clearances)
    clearances.setdefault(UNASSIGNED_NETCLASS, default_clearance_mm)
    live = sorted(widths)

    def stamp(marked: str, searching: str) -> float:
        return max(table.required(marked, searching), clearances.get(marked, 0.0))

    signatures: dict[tuple, str] = {}
    profile_of_class: dict[str, str] = {}
    profile_width: dict[str, float] = {}
    for net_class in live:
        signature = (
            tuple(round(stamp(other, net_class), 6) for other in live),
            round(widths[net_class], 6),
        )
        key = signatures.get(signature)
        if key is None:
            key = net_class
            signatures[signature] = key
            profile_width[key] = widths[net_class]
        profile_of_class[net_class] = key

    return ClearanceProfiles(
        profile_of_class=profile_of_class,
        profile_width_mm=profile_width,
        class_clearance_mm=clearances,
        table=table,
    )
