"""Single source of truth for per-layer PCB roles (signal vs. power/jumper),
parsed from ``pcb/temper.kicad_pcb``'s own ``(layers ...)`` block.

**The gap this closes.** Before this module existed, "In1.Cu/In2.Cu are power
planes" was true only in the board file's own declaration
(``(layers (1 "In1.Cu" power) ...)``) and in scattered prose -- nothing in
this repo's Python or Rust board readers ever parsed that role token.
``io/_parse_board.py``'s ``_extract_stackup`` derives a layer's routability
purely from structural position (first/last copper layer = "signal") or from
whether a plane-required net's zone happens to sit on it, and
``packages/temper-design-bundle/src/parse_engine.rs``'s ``raw_board_from_tree``
reads a layer's *name* at index 1 of each ``(N "Name" role ...)`` entry and
discards the *role* token at index 2 entirely (documented independently by
``scripts/check_layer_plane_emission_coverage.py``'s PROPERTY 1). So the
declaration in the board file and every downstream consumer's idea of "which
layers are signal" could silently disagree, and did: the router's actual
signal-layer set (``{"F.Cu", "B.Cu"}``) was a hardcoded constant in at least
three places (``router_v6/channel_mapping.py``, ``router_v6/_astar_nlayer.py``,
``router_v6/_zone_pour_stitch.py``) that happened to match the board's
declared roles, by construction, never by a checked relationship -- so a
future stackup edit (e.g. this repo's 2026-08-13 6-layer decision,
``docs/evidence/2026-08-13-layer-architecture-decision.md``) had no
mechanism to propagate itself to any of them.

This module is a narrow, direct, dependency-light reader of the *declaration*
only -- it does not go through ``_extract_stackup``'s zone-content heuristic
or the Rust parse engine at all (deliberately: that machinery answers a
different question, "what should THIS PARSED BOARD's existing copper be
classified as for obstacle-map purposes", and is mid-migration with a
documented, tested danger zone around flipping its own
``use_declared_layer_roles`` flag before pours become derived output -- see
that function's own docstring). This module answers a narrower, purely
declarative question instead: "what role did the board file itself declare
for this layer name", nothing more -- the same scope
``scripts/check_stackup_copper_weight_gate.py`` already uses for the
``(setup (stackup ...))`` block, applied here to the sibling ``(layers ...)``
block.

**Two different questions, two different accessors -- do not conflate them.**

- :func:`signal_layer_names` answers "what does the board's stackup
  *declare*": every ``.Cu``-suffixed layer whose role token is ``signal``,
  in declared order. This is what a layer-*architecture* decision (adding or
  removing signal layers) should be measured against -- e.g. the routing-
  capacity utilisation gate this module also backs
  (``scripts/check_layer_utilization_gate.py``) uses this, not the narrower
  accessor below, because the gate exists to catch exactly this mismatch
  between "how many signal layers are declared" and "how much capacity the
  routed netlist needs" -- collapsing it to "how many the router engine
  currently supports" would silently hide the same class of gap this module
  exists to close.
- :func:`routable_signal_layers` answers "what can the ROUTER actually target
  today": the intersection of the declaration above with
  :data:`ENGINE_SUPPORTED_SIGNAL_LAYERS`, a small, explicit, hand-maintained
  set representing the router's real occupancy-grid/A*-pathfinding coverage.
  Declaring a new signal layer in the board file does not, by itself, give
  the production router (``router_v6``) the Stage-2 occupancy grid or
  Stage-4 pathfinding support to place a single trace on it -- that is real
  infrastructure work, out of scope for a layer-architecture *declaration*
  change (see the evidence doc's Sec 6.4). Call sites that decide where the
  router may *actually* place copper (zone-pour emission, A* grid
  selection) must use this accessor, not the bare declaration, or a stackup
  edit alone could make the router attempt to route on a layer with no
  geometric support -- the exact failure mode a documented 2026-07-28
  regression (``docs/evidence/2026-07-28-stackup-partial-revert.md``, cited
  in ``_extract_stackup``'s own docstring) already produced once for a
  related migration.

Both accessors are typed via :class:`LayerRole` rather than a bare string, so
a caller asking "can I route on In1.Cu" gets ``LayerRole.POWER`` back, not a
string that happens to read "power" this week.
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path

__all__ = [
    "ENGINE_SUPPORTED_SIGNAL_LAYERS",
    "ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED",
    "LayerRole",
    "is_signal_layer",
    "parse_declared_layer_roles",
    "parse_declared_layer_roles_from_path",
    "routable_signal_layers",
    "routable_signal_layers_from_path",
    "signal_layer_names",
    "signal_layer_names_from_path",
]


class LayerRole(Enum):
    """A copper layer's declared role, per ``pcb/temper.kicad_pcb``'s own
    ``(layers ...)`` block. The KiCad board-format vocabulary
    (``kicad_pcb`` v20211014, this repo's format) is ``signal``, ``power``,
    ``mixed``, ``jumper``, or ``user`` (non-copper layers only ever declare
    ``user``, filtered out before reaching this type -- see
    :func:`parse_declared_layer_roles`).
    """

    SIGNAL = "signal"
    POWER = "power"
    MIXED = "mixed"
    JUMPER = "jumper"

    @property
    def is_routable_role(self) -> bool:
        """Whether THIS ROLE, in isolation, is a role the router may ever
        target -- ``SIGNAL`` or ``MIXED`` only. This is necessary but not
        sufficient for "the router can route here today": see
        :func:`routable_signal_layers`, which additionally intersects with
        the engine's real capability.
        """
        return self in (LayerRole.SIGNAL, LayerRole.MIXED)


# The router's real occupancy-grid/A*-pathfinding coverage today. Every
# module that hardcoded a 2-layer signal set before this module existed
# (``router_v6/channel_mapping.py``, ``router_v6/_astar_nlayer.py``,
# ``router_v6/_zone_pour_stitch.py``) hardcoded exactly this pair -- this
# constant is the single place that fact now lives, so widening the
# router's real capability (adding Stage-2 grid + Stage-4 pathfinding
# support for a new signal layer) is a one-line change here, propagating
# automatically to every caller of :func:`routable_signal_layers` rather
# than requiring a hunt through the router for hardcoded layer lists again.
#
# Two forms, deliberately: the ordered tuple is authoritative (F.Cu first
# matches every prior hardcoded literal this replaces, several of which
# index ``[0]`` as a "preferred/default layer" -- see
# ``_zone_pour_stitch.py``'s own call site -- so silently reordering via
# ``sorted(frozenset(...))`` would be a real behavior change, not a
# refactor); the frozenset is for plain membership/intersection checks
# (:func:`routable_signal_layers`) where order doesn't matter and a set is
# the more honest type.
#
# UNFROZEN 2026-08-13 (docs/evidence/2026-08-13-router-nlayer-routing.md):
# this constant was pinned at ``("F.Cu", "B.Cu")`` even after PR #1178 (the
# 2026-08-13 6-layer stackup decision) declared ``In3.Cu``/``In4.Cu``
# signal -- so the gate this module exists to close (a stackup edit having
# no mechanism to propagate to the router) reproduced inside the module
# built to close it. Widened to the real, verified engine capability:
#
# - Stage 2 occupancy-grid construction (``routing_space.py``'s
#   ``compute_routing_space`` / ``occupancy_grid.py``'s
#   ``build_occupancy_grid``) already builds one grid per
#   ``pcb.stackup.layers`` entry whose ``layer_type`` is
#   ``"signal"``/``"mixed"`` -- genuinely N-layer, no per-layer-name
#   literal anywhere in that path.
# - The via-aware A* search primitive (``astar_core._route_segment_3d`` /
#   ``_astar_search_3d``) already accepts an arbitrary-size
#   ``grids: dict[str, OccupancyGrid]`` and costs a layer transition (via)
#   generically; ``_astar_nlayer.py``'s ``select_routing_grids_nlayer`` /
#   ``run_astar_pathfinding_nlayer`` thread this through a real per-net
#   driver, tested (``test_astar_nlayer.py``,
#   ``test_astar_route_multilayer_via_fallback.py``).
# - Via placement (``via_placement.py``'s ``_place_vias_for_path``)
#   already derives each via's ``from_layer``/``to_layer`` from the
#   routed path's own actual segment layers (``temper_geometry``'s
#   ``via_layer_pair_py``), not a hardcoded F.Cu/B.Cu pair.
#
# What is NOT included here, deliberately: ``In1.Cu``/``In2.Cu``. Those are
# declared ``power`` in ``pcb/temper.kicad_pcb``'s own ``(layers ...)``
# block, not ``signal`` -- :func:`signal_layer_names` already excludes them
# from the *declared-architecture* half of :func:`routable_signal_layers`'s
# intersection, so widening this engine-capability set to include them
# would not change ``routable_signal_layers``'s output for this board. It
# would, however, silently change the result for any *other* board that
# happens to declare an inner layer ``signal`` while genuinely meaning it
# as a plane -- so this constant is kept to the layer names actually
# verified above, not padded out "just in case."
#
# What layer_assignment.py's soft *preferred*-layer heuristic (channel_
# mapping._assign_layer / the 4-element Layer enum L1_TOP..L4_BOT, 1:1
# mapped to F.Cu/In1.Cu/In2.Cu/B.Cu) still does NOT cover: a net's SSOT
# preferred layer can only ever resolve to F.Cu or B.Cu today (see that
# module's docstring). This is a soft optimization hint, not a hard
# capability cap -- tiers 2/3 of the N-layer A* try every other available
# grid regardless of what tier 1's preferred layer was -- so it is left
# alone here; see the router-nlayer-routing evidence doc for the full
# argument.
ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED: tuple[str, ...] = ("F.Cu", "In3.Cu", "In4.Cu", "B.Cu")
ENGINE_SUPPORTED_SIGNAL_LAYERS: frozenset[str] = frozenset(ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED)

# Matches one `(layers ...)` entry: an ordinal, a quoted KiCad layer name,
# and a bareword role token (optionally followed by a quoted display name,
# e.g. `(32 "B.Adhes" user "B.Adhesive")` -- the display name is not
# captured, this module has no use for it).
_LAYER_ENTRY_RE = re.compile(r'\(\s*\d+\s+"([A-Za-z0-9_.]+)"\s+(\w+)')

_COPPER_ROLE_NAMES = {r.value for r in LayerRole}


def _extract_balanced(text: str, marker: str) -> str:
    """Return the balanced-parenthesis span starting at the first
    occurrence of ``marker`` in ``text``. Mirrors
    ``check_stackup_copper_weight_gate.py``'s identically-named helper
    (small enough, and specific enough to this exact S-expression
    slicing task, that sharing it would need a new shared module for one
    ~15-line function used by two callers -- not worth the indirection).
    """
    start = text.find(marker)
    if start == -1:
        raise ValueError(f"no {marker!r} block found")
    depth = 0
    end = None
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise ValueError(f"{marker!r} block is not balanced")
    return text[start:end]


def parse_declared_layer_roles(pcb_content: str) -> dict[str, LayerRole]:
    """Parse ``pcb/temper.kicad_pcb``'s top-level ``(layers ...)`` block
    directly and return ``{layer_name: LayerRole}`` for every ``.Cu``
    layer whose role is one of :class:`LayerRole`'s members, in declared
    order (``dict`` insertion order, Python 3.7+ guarantee).

    Non-copper layers (``F.SilkS``, ``Edge.Cuts``, ...) always declare role
    ``user``, which is not a :class:`LayerRole` member -- they are silently
    skipped rather than raising, since this function's whole contract is
    about copper roles specifically.

    Raises:
        ValueError: the board content has no ``(layers ...)`` block, the
            block is unbalanced, or NO ``.Cu`` layer with a recognized role
            is found at all (a fail-closed signal that something is
            structurally wrong with the input, not an empty-but-valid
            board).
    """
    block = _extract_balanced(pcb_content, "(layers")

    roles: dict[str, LayerRole] = {}
    for name, role_token in _LAYER_ENTRY_RE.findall(block):
        if not name.endswith(".Cu"):
            continue
        if role_token not in _COPPER_ROLE_NAMES:
            continue
        roles[name] = LayerRole(role_token)

    if not roles:
        raise ValueError(
            "no '.Cu' layer with a recognized role (signal/power/mixed/jumper) "
            "found in the board's (layers ...) block"
        )
    return roles


def parse_declared_layer_roles_from_path(board_path: Path) -> dict[str, LayerRole]:
    """:func:`parse_declared_layer_roles`, reading ``board_path`` first.
    For scripts/gates/tests with a real file on disk; library code that
    already has board content in hand should call the content-taking form
    directly rather than re-reading the file.
    """
    return parse_declared_layer_roles(Path(board_path).read_text(encoding="utf-8"))


def signal_layer_names(pcb_content: str) -> list[str]:
    """Every ``.Cu`` layer the board declares with role ``signal`` (NOT
    ``mixed`` -- a board that ever declares a layer ``mixed`` is asking a
    question this function deliberately does not answer for it; see
    :meth:`LayerRole.is_routable_role` for the routable-role superset), in
    declared order. This is the *architecture* question -- see this
    module's docstring for why the utilisation gate uses this accessor and
    not :func:`routable_signal_layers`.
    """
    roles = parse_declared_layer_roles(pcb_content)
    return [name for name, role in roles.items() if role is LayerRole.SIGNAL]


def signal_layer_names_from_path(board_path: Path) -> list[str]:
    """:func:`signal_layer_names`, reading ``board_path`` first."""
    return signal_layer_names(Path(board_path).read_text(encoding="utf-8"))


def routable_signal_layers(pcb_content: str) -> list[str]:
    """Every declared ``signal`` layer the router can ACTUALLY target today
    -- the intersection of :func:`signal_layer_names` with
    :data:`ENGINE_SUPPORTED_SIGNAL_LAYERS`, in declared order. This is the
    *routing-decision* question -- production call sites that pick which
    layer(s) get real copper (zone-pour emission, A* grid selection) should
    use this, not the bare declaration. See this module's docstring for the
    full argument.
    """
    supported = ENGINE_SUPPORTED_SIGNAL_LAYERS
    return [name for name in signal_layer_names(pcb_content) if name in supported]


def routable_signal_layers_from_path(board_path: Path) -> list[str]:
    """:func:`routable_signal_layers`, reading ``board_path`` first."""
    return routable_signal_layers(Path(board_path).read_text(encoding="utf-8"))


def is_signal_layer(layer_name: str, pcb_content: str) -> bool:
    """Typed answer to "can I route on ``layer_name`` (per the board's own
    ARCHITECTURE declaration)" -- ``True`` iff the board declares
    ``layer_name`` with role ``signal``. Returns ``False`` for a
    ``power``/``mixed``/``jumper`` layer, and for any name the board does
    not declare at all (never raises for an unknown name -- "is this
    unknown thing routable" is unambiguously "no", not an error).

    This answers the architecture question, matching
    :func:`signal_layer_names`; a caller asking the narrower "can the
    router actually place a trace here today" question should check
    membership in :func:`routable_signal_layers` instead.
    """
    try:
        roles = parse_declared_layer_roles(pcb_content)
    except ValueError:
        return False
    return roles.get(layer_name) is LayerRole.SIGNAL
