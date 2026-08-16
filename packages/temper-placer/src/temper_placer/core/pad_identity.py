"""Physical-pad identity -- the single source of truth for resolving a
``(component_ref, pin_number)`` pair to ONE physical pad.

**The problem this module exists to solve.** ``(ref, pin_number)`` reads
like a unique key for "the physical pad" everywhere this codebase uses it
-- ``Net.pins``, dozens of ``for comp_ref, pin_name in net.pins:`` loops,
``Component.get_pin`` (the pyo3 method, ``netlist_contracts.rs``). It is
not one. A footprint can fabricate more than one physical solder pad under
the same pad number/name, and this board does: K2/K3
(``temper:Relay_SPDT_Schrack-RT314012``) duplicate pads "1", "3", and "4"
-- two physical holes 7.5mm apart per logical contact, wired in parallel
for 16A current sharing. K1 (``temper:Relay_SPST_Omron-G4A-E``) duplicates
pad number ``""`` four times (NPTH mechanical mounting holes, no net).
``Component.get_pin(name)`` always returns its FIRST name/number match;
calling it once per ``net.pins`` occurrence silently collapses two
distinct physical terminals onto one coordinate. That exact mechanism let
the router print "routed successfully" for
``discharge.k_dis1-no``/``discharge.k_dis2-no`` while writing zero
connecting copper -- see
``scripts/check_net_pin_identity_pad_correspondence.py`` and
``router_v6/pad_connectivity_audit.find_pin_identity_pad_mismatches`` for
the incident this was first caught and fixed under (PR #1177).

**The identity decision.** Physical pad identity is ``(ref, pin_number,
occurrence)`` -- :class:`PadOccurrence` -- where ``occurrence`` is the
0-indexed position among SAME-numbered pins, in ``Component.pins``
encounter order. ``net.pins`` and ``comp.pins`` are both built by the same
encounter-order iteration over a component's raw pad list
(``extract_nets_pure`` / ``parse_engine.rs``), so the Nth occurrence of
``(comp_ref, pin_name)`` within a given net's ``pins`` corresponds exactly
to the Nth name/number-matching pin in that component's own ``pins`` list.
This needs no new field and no pyo3 boundary change, and is stable across
re-parses of an unmodified board (the file's own pad order is
deterministic) and stable against unrelated board edits: a pin with a
DIFFERENT number added anywhere in the footprint never changes another
pin's occurrence index, since only same-number pads increment it.
Candidates rejected: raw position (it's the thing being computed, not a
usable input key -- every caller that has a pad in hand only has
``(ref, pin_number)``, never a coordinate, to look it up by); an opaque
``PadId`` assigned at parse time (would need a new field crossing the
Rust/Python pyo3 boundary on every mirrored ``Pin`` struct for a benefit
``occurrence`` already provides -- rejected as disproportionate, the same
judgment PR #1167 made rejecting a full pyo3 retype of
``initial_rotation``).

**Auditing every consumer of ``net.pins``/``Component.get_pin`` found the
identical first-match-only mistake independently reimplemented in at
least five more places** (``router_v6/_pipeline_grid.py`` -- fixed by PR
#1177 with a local, one-off ``_nth_matching_pin`` -- plus, still unfixed
before this module, ``router_v6/bundle_analyzer.py``,
``router_v6/capacity_check.py``, ``router_v6/layer_assignment.py``,
``router_v6/resource_bound.py``, and ``validation/metrics.py``), each a
separate, silent restatement of the same wrong assumption, none aware of
the others. This module is the single canonical implementation; every one
of those call sites now delegates here instead of re-deriving its own
occurrence bookkeeping. Two more call sites were found and are NOT fixed
here -- see ``docs/evidence/2026-08-13-pad-identity-ssot.md`` for why
(cross-language pinned-oracle/differential entanglement that PR
#1136/#1137's lesson says must not be touched on one arm alone):
``temper-rust-router/src/terminal_planning.rs::extract_net_terminals``
(Rust-native reimplementation of the same first-match shortcut, on the
LIVE terminal-extraction path) and
``temper-orchestration/src/pipeline_route.rs::run_collect_pad_positions``
(a Rust port of a pinned Python oracle that calls ``get_pin`` the same
way -- its ROTATION omission was fixed 2026-08-15, see
``docs/evidence/2026-08-15-router-pad-avoidance-fix.md``; the first-match
occurrence collapse remains deferred).

**Where the matching predicate itself lives.** "Does this pin's name or
number equal X" is answered by the Rust ``Component.get_pin_occurrences``
method (``netlist_contracts.rs``, added alongside this module) -- the
actual SSOT for "what does a pin name/number match" (it, not this module,
owns the ``pin.name == X or pin.number == X`` comparison). This module
adds only the occurrence bookkeeping and disambiguation POLICY that is
inherently about a Python-level list (``net.pins``) or about how a
*caller* wants ambiguity handled, neither of which the Rust component
object has an opinion on. See ``pad_occurrence::PadOccurrence`` (Rust,
``temper-design-bundle``) for the analogous typed identity on that side --
pure infrastructure for future Rust-side pad resolution, not currently
called from Rust production code (``grep -rn "\\.get_pin("`` across every
``*.rs`` in this workspace finds zero real Rust call sites through this
API; ``terminal_planning.rs`` reimplements the comparison inline instead,
one of the two deferred findings above).

**The three ways to resolve a pin, and when to use which:**

- :func:`nth_matching_pin` / :func:`resolve_net_pins` -- you are walking a
  net's own ``pins`` list and need EVERY occurrence resolved to its own
  distinct physical pad, including duplicates, with the occurrence index
  threaded through explicitly. This is what routing, geometry, and
  metrics code needs, and what every fixed call site in this module's
  docstring above uses.
- :func:`get_unique_pin` -- you want "the" pin for a name/number and would
  be silently wrong if there were two, and have no occurrence context to
  supply. Raises :class:`AmbiguousPinError` instead of guessing -- this is
  the Part-3 "make it unrepresentable" enforcement this module provides:
  a caller can no longer silently receive pad-3-of-2 the way
  ``Component.get_pin`` always did. There is deliberately NO function in
  this module that takes a bare ``(comp, pin_number)`` and returns a
  single pin without either an explicit occurrence or a willingness to
  raise on ambiguity -- that shape (silently default to occurrence 0) is
  exactly the footgun being removed.
- :func:`iter_matching_pins` -- you want every physical pad matching a
  name/number without any positional/occurrence semantics attached (e.g.
  net-membership checks, where every duplicate shares the same net by
  construction and any one of them answers the question correctly --
  ``core/loop_extractor.py``'s ``get_pin_net`` is this case, audited and
  left on ``Component.get_pin`` deliberately, see its own docstring).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from temper_placer.core.netlist import Component, Net, Pin

__all__ = [
    "AmbiguousPinError",
    "PadOccurrence",
    "duplicate_pad_numbers",
    "get_unique_pin",
    "iter_matching_pins",
    "iter_pin_occurrences",
    "net_pad_positions",
    "net_pin_occurrence_indices",
    "nth_matching_pin",
    "resolve_net_pins",
]


class PadOccurrence(NamedTuple):
    """The canonical, unambiguous identity of one physical pad.

    Use this -- never a bare ``(ref, pin_number)`` tuple -- whenever code
    needs to key or compare pads as physically distinct things (a cache, a
    diagnostic report, a set of "pads already visited"). A bare
    ``(ref, pin_number)`` tuple is exactly the representation that let two
    distinct physical pads collapse to one key throughout this codebase;
    ``occurrence`` is the field that was missing.
    """

    ref: str
    pin_number: str
    occurrence: int


class AmbiguousPinError(Exception):
    """Raised by :func:`get_unique_pin` when a pin name/number matches
    more than one physical pad on a component -- the caller asked for
    "the" pin as if ``(ref, pin_number)`` were a unique key, and on this
    component, for this number, it is not. There is no default answer:
    silently returning the first match is exactly the bug this module
    exists to remove (see module docstring). Callers that legitimately
    need to handle every occurrence should use :func:`iter_matching_pins`
    or :func:`resolve_net_pins` instead of catching this.
    """

    def __init__(self, comp: Component, pin_number: str, count: int) -> None:
        self.ref = getattr(comp, "ref", "?")
        self.pin_number = pin_number
        self.count = count
        super().__init__(
            f"{self.ref!r} has {count} pins matching {pin_number!r} -- "
            "ambiguous; use iter_matching_pins/resolve_net_pins to handle "
            "every occurrence explicitly instead of assuming there is one"
        )


def iter_matching_pins(comp: Component, pin_number: str) -> list[Pin]:
    """Every pin on *comp* whose ``name`` or ``number`` equals
    *pin_number*, in ``comp.pins`` encounter order.

    Delegates the actual matching to the Rust
    ``Component.get_pin_occurrences`` method (the SSOT predicate, see
    module docstring) when available; falls back to a plain Python scan
    for test doubles / fixtures that don't implement it.
    """
    get_occurrences = getattr(comp, "get_pin_occurrences", None)
    if get_occurrences is not None:
        return list(get_occurrences(pin_number))
    return [
        pin
        for pin in (getattr(comp, "pins", None) or ())
        if pin is not None
        and (getattr(pin, "name", None) == pin_number or getattr(pin, "number", None) == pin_number)
    ]


def nth_matching_pin(comp: Component, pin_number: str, occurrence: int) -> Pin | None:
    """Return the *occurrence*-th (0-indexed) pin on *comp* whose ``name``
    or ``number`` equals *pin_number*, or ``None`` if fewer than
    ``occurrence + 1`` pins match.

    *occurrence* has no default -- a caller must always say which physical
    pad it means. This is the correspondence :func:`resolve_net_pins`
    relies on: the Nth occurrence of ``(comp_ref, pin_name)`` within a
    net's own ``pins`` corresponds exactly to the Nth name/number-matching
    pin in that component's own ``pins`` list (see module docstring).
    """
    matches = iter_matching_pins(comp, pin_number)
    if occurrence < 0 or occurrence >= len(matches):
        return None
    return matches[occurrence]


def get_unique_pin(comp: Component, pin_number: str) -> Pin | None:
    """Return the ONE pin on *comp* matching *pin_number*, or ``None`` if
    no pin matches.

    Raises :class:`AmbiguousPinError` if more than one pin matches --
    unlike ``Component.get_pin``, this never silently picks the first of
    several. Use this only where the caller's logic genuinely does not
    care WHICH physical occurrence answers the question (e.g. "does this
    component have a pin named DRAIN, and if so what net is it on" -- true
    regardless of which physical occurrence answers it, since every
    occurrence of a duplicated pad number shares one net by construction);
    anywhere position/geometry is involved, use :func:`resolve_net_pins`
    or :func:`nth_matching_pin` instead, since those callers care WHICH
    physical pad, not just whether one exists.
    """
    matches = iter_matching_pins(comp, pin_number)
    if not matches:
        return None
    if len(matches) > 1:
        raise AmbiguousPinError(comp, pin_number, len(matches))
    return matches[0]


def iter_pin_occurrences(comp: Component) -> Iterator[tuple[PadOccurrence, Pin]]:
    """Yield ``(PadOccurrence, Pin)`` for every physical pin on *comp*, in
    ``comp.pins`` encounter order -- the per-component enumeration the
    duplicate-pad-number survey and the fail-closed gate use to name every
    physical pad unambiguously, including duplicates.
    """
    ref = getattr(comp, "ref", "?")
    seen: dict[str, int] = {}
    for pin in getattr(comp, "pins", None) or ():
        if pin is None:
            continue
        number = getattr(pin, "number", None)
        if number is None:
            number = getattr(pin, "name", None)
        if number is None:
            continue
        occurrence = seen.get(number, 0)
        seen[number] = occurrence + 1
        yield PadOccurrence(ref=ref, pin_number=number, occurrence=occurrence), pin


def duplicate_pad_numbers(comp: Component) -> dict[str, int]:
    """``{pin_number: count}`` for every pad number *comp* declares more
    than once -- the per-component shape the duplicate-pad-number survey
    (Part 1 of the pad-identity audit) and the fail-closed gate both scan
    for. Iterates ``comp.pins`` directly (the real, position-bearing pin
    objects), not name-based lookup, so it needs no disambiguation itself.
    """
    counts: dict[str, int] = {}
    for pin in getattr(comp, "pins", None) or ():
        if pin is None:
            continue
        number = getattr(pin, "number", None)
        if number is None:
            number = getattr(pin, "name", None)
        if number is None:
            continue
        counts[number] = counts.get(number, 0) + 1
    return {number: count for number, count in counts.items() if count > 1}


def net_pin_occurrence_indices(pins: Sequence[tuple[str, str]]) -> list[int]:
    """For each ``(ref, pin_number)`` entry in *pins* (a ``Net.pins``-shaped
    list, in its own encounter order), return which occurrence of that
    exact tuple it is -- 0 for the first time a given ``(ref, pin_number)``
    appears in *pins*, 1 for the second, and so on.

    Pure function over the tuple list alone (no component lookup), so it
    is trivial to test and reuse independently of pad resolution.
    """
    seen: dict[tuple[str, str], int] = {}
    indices: list[int] = []
    for key in pins:
        occurrence = seen.get(key, 0)
        indices.append(occurrence)
        seen[key] = occurrence + 1
    return indices


def resolve_net_pins(
    net: Net, comp_by_ref: Mapping[str, Component]
) -> Iterator[tuple[str, str, Pin | None]]:
    """Yield ``(comp_ref, pin_number, pin)`` for every entry in
    ``net.pins``, in order, with *pin* resolved to the correct DISTINCT
    physical pin via occurrence-indexed lookup -- the general-purpose
    replacement for a hand-rolled ``for comp_ref, pin_name in net.pins:
    pin = comp.get_pin(pin_name)`` loop (that pattern is exactly the
    duplicate-pad-number bug; see module docstring).

    *pin* is ``None`` when *comp_ref* is missing from *comp_by_ref*, or
    when the component has no matching pin, or fewer matching pins than
    this occurrence needs -- callers should handle it the same way they
    would have handled ``get_pin`` returning ``None``.
    """
    pins = list(getattr(net, "pins", []) or [])
    occurrence_indices = net_pin_occurrence_indices(pins)
    for (comp_ref, pin_number), occurrence in zip(pins, occurrence_indices, strict=True):
        comp = comp_by_ref.get(comp_ref)
        pin = nth_matching_pin(comp, pin_number, occurrence) if comp is not None else None
        yield comp_ref, pin_number, pin


def net_pad_positions(net: Net, comp_by_ref: Mapping[str, Component]) -> list[tuple[float, float]]:
    """Resolve a Net's pads to world coordinates via component lookup.

    A shared, ``pin_world_position``-based implementation of the same
    computation several call sites build locally (some via
    :func:`resolve_net_pins` plus their own position math, e.g.
    ``capacity_check._net_pad_positions``, which deliberately keeps a
    non-rotation-aware raw-offset formula this function does NOT
    replicate -- see that module's own docstring); provided here for any
    NEW call site so a further local reimplementation never gets a chance
    to exist. Pads whose component is missing from *comp_by_ref*, or which
    lack a resolvable position, are skipped silently; a pin that fails to
    resolve falls back to the component's own position (matching
    ``_pipeline_grid._net_pad_positions``'s pre-existing contract, which
    this function now implements for that module).
    """
    from temper_placer.core.pin_geometry import pin_world_position

    positions: list[tuple[float, float]] = []
    for comp_ref, _pin_number, pin in resolve_net_pins(net, comp_by_ref):
        comp = comp_by_ref.get(comp_ref)
        if comp is None:
            continue
        comp_pos = getattr(comp, "initial_position", None)
        if comp_pos is None:
            continue
        if pin is None:
            positions.append((float(comp_pos[0]), float(comp_pos[1])))
            continue
        wx, wy = pin_world_position(pin, comp)
        positions.append((float(wx), float(wy)))
    return positions
