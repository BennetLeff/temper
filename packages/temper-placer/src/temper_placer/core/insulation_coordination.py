"""Load ``elec/insulation_manifest.yaml`` and answer "how far apart must
these two nets be?" -- per pairing, or "cannot be determined".

This module is the *thin* half of the mechanism. Every rule that matters --
the schema, the placeholder checks, the staleness (content-digest) check, the
completeness rule, the insulation-class derivation, the Table 17/18 lookups,
the clause-29.2.3 doubling and the 30 kHz frequency ceiling -- lives in Rust,
in ``packages/temper-design-bundle/src/insulation.rs``, and is reached through
``temper_design_bundle_python.resolve_insulation_declaration``. Read that
module's docstring for the derivation, the standards citations, and the
argument for each check. Nothing here re-implements any of it: a second Python
home for a safety rule is exactly what AGENTS.md forbids, and this particular
rule already had four homes' worth of drift behind it (``MIN_BARRIER_WIDTH_MM``,
``HV_CREEPAGE_ENFORCED_MM``, ``HV_LV_CREEPAGE_MM``, and the REQ-SAFE-01
matrix).

What this module *does* own, because Rust deliberately does not:

* **Finding the declaration.** One repo-relative path, resolved from this
  file's own location, with no environment-variable override -- an env var
  that can redirect a safety declaration is a hole, not a feature.
* **Naming the enforced pollution degree.** See
  :data:`ENFORCED_POLLUTION_DEGREE`.
* **Reducing a per-net requirement to a per-net-class one**, conservatively.
  See :func:`requirement_for_net_classes`.

Three-valued, and that is the point
-----------------------------------
This board switches at 47 kHz, above IEC 60664-1 cl. 1.1.1's 30 kHz scope
ceiling, and cl. 2.3 routes dimensioning above it to IEC 60664-4 -- paywalled
and not obtained. Every pairing that touches the switch node or the resonant
tank therefore has **no determinable requirement**. Such a pairing carries:

* ``requirement_mm() -> nan`` -- not a number, and every ``measured >= nan``
  comparison is ``False``, which is the fail-closed direction;
* ``enforceable_floor_mm()`` -- the ``<=30 kHz`` table figure, a **proven
  lower bound**, not a pass criterion;
* ``is_determinable() -> False``;
* ``grade(measured) -> "INDETERMINATE"`` for any measurement at or above the
  floor -- **never** ``"PASS"``.

A consumer that wants a geometric constraint should use
``enforceable_floor_mm()``; a consumer that wants to *certify* must check
``is_determinable()`` first and report "cannot determine" when it is false.
There is no third option in which an indeterminate pairing passes.

Fail-closed contract
--------------------
Every failure raises :class:`InsulationDeclarationError` (a ``RuntimeError``).
There is no fallback value, no default pairing and no "warn and continue"
path -- the only thing a silent fallback could produce is a safety number
chosen by something other than the declaration. Concretely, all of these are
hard errors:

* the declaration file is missing, empty, unparseable, or has an unknown
  schema version;
* it carries an unknown key (including a hand-written requirement: declaring
  the answer next to the evidence is the defect this replaces);
* a verification field is blank or a placeholder;
* ``measured_at_commit`` is not 40 lowercase hex characters;
* the declared facts do not match ``declared_state_sha256`` -- i.e. a working
  voltage or a group membership was edited after the verification that backs
  it;
* any unordered pair of declared groups, **including self-pairs**, has no
  pairing entry.

What this cannot do
-------------------
See :func:`limitation`. Two structural limits, neither closable by code: the
47 kHz requirement is *unknown, not satisfied* (it needs a standard this
project must buy), and the tank<->SELV working voltage has never been
measured in this repository.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import temper_design_bundle_python as _tdb

__all__ = [
    "DECLARATION_PATH",
    "ENFORCED_POLLUTION_DEGREE",
    "InsulationDeclarationError",
    "NetClassRequirement",
    "barrier_floor_mm",
    "barrier_is_determinable",
    "limitation",
    "net_domain",
    "requirement_for_class_to_domain",
    "requirement_for_net_classes",
    "requirement_for_nets",
    "resolve_declaration",
]


class InsulationDeclarationError(RuntimeError):
    """The insulation declaration is missing, malformed, stale, or incomplete.

    Deliberately a subclass of ``RuntimeError`` rather than a bare
    ``ValueError``: it is raised at import time by
    :mod:`temper_placer.core.isolation_constants`, and a distinct type lets a
    caller (or a test) tell "the declaration is broken" apart from any other
    ``ValueError`` crossing the pyo3 boundary.
    """


# The declaration lives beside elec/domain_manifest.yaml -- the working
# precedent this file's shape follows, and where a reader looking for "what
# does this design declare about itself" already looks.
#
# Resolved from this module's own location, never from the cwd and never from
# an environment variable: an env var that can redirect a safety declaration
# is a hole, not a feature, and a cwd-relative path would make the enforced
# creepage figures depend on where a script happened to be invoked from.
_RELATIVE = Path("elec") / "insulation_manifest.yaml"


def _discover_repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / _RELATIVE).is_file():
            return candidate
    # Five parents up from
    # packages/temper-placer/src/temper_placer/core/insulation_coordination.py
    # is the repo root under this repo's editable install. The ancestor walk
    # above is a robustness measure for any layout where that arithmetic does
    # not hold; it does NOT weaken anything -- if no ancestor carries the
    # declaration, this fixed arithmetic still supplies a path, and reading it
    # fails closed with InsulationDeclarationError. There is no branch here
    # that yields a requirement without a declaration.
    return here.parents[5]


_REPO_ROOT = _discover_repo_root()
DECLARATION_PATH = _REPO_ROOT / _RELATIVE


# The pollution degree the creepage tables are read at.
#
# ONE LITERAL, AND IT IS DELIBERATELY A SEAM. Pollution degree is a property
# of the *enclosure*, not of the netlist, so it does not belong in
# `elec/insulation_manifest.yaml` and `insulation.rs` takes it as an input
# rather than reading it. PD3 is this project's enforced classification --
# `docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md`: the as-built
# board is forced-air vented with no cover, gasket or partition, so PD3
# governs per IEC 60335-2-6 cl. 29.2 Addition, whose PD2 exception requires a
# sealed compartment that does not exist
# (`docs/evidence/2026-08-11-pd2-decision-record.md`).
#
# `scripts/check_insulation_pairings.py` cross-checks this against
# `scripts/generate_kicad_dru.py`'s own PD selector
# (`HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD3_MM`, the line
# `scripts/check_pd2_compartment_evidence.py` already treats as the repo's PD
# selection point) and fails if the two disagree, so this literal cannot drift
# away from the fab-authoritative one silently.
#
# WHEN `feat/enclosure-declaration-derives-pd` LANDS: delete this constant and
# call `temper_placer.core.enclosure_declaration.resolve_declaration()
# .pollution_degree` instead. That branch derives PD from a declared, dated,
# commit-anchored enclosure claim and its own gate rejects "a hand-written
# pollution_degree" -- this constant is exactly that, kept only because that
# branch is not merged and inventing a second enclosure declaration here would
# be the duplication AGENTS.md forbids.
ENFORCED_POLLUTION_DEGREE = 3


@lru_cache(maxsize=1)
def _declaration_text() -> str:
    try:
        return DECLARATION_PATH.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise InsulationDeclarationError(
            f"insulation declaration not found at {DECLARATION_PATH}. This file "
            "is what supplies the working voltage of every net pairing on this "
            "board, and therefore every creepage requirement derived from it; "
            "without it no requirement can be derived and none is assumed. See "
            "packages/temper-design-bundle/src/insulation.rs."
        ) from exc
    except OSError as exc:
        raise InsulationDeclarationError(
            f"insulation declaration at {DECLARATION_PATH} could not be read: {exc}"
        ) from exc


def resolve_declaration(
    path: Path | None = None, pollution_degree: int | None = None
) -> Any:
    """Read, validate and evaluate the insulation declaration at *path*.

    *path* defaults to :data:`DECLARATION_PATH`; *pollution_degree* to
    :data:`ENFORCED_POLLUTION_DEGREE`. Both are explicit parameters rather than
    environment lookups so a test can point at a fixture without any global
    switch existing that production could also be flipped by.

    Returns the Rust ``InsulationResolution``. Raises
    :class:`InsulationDeclarationError` on every failure; never returns a
    fallback.
    """
    text = _declaration_text() if path is None else Path(path).read_text(encoding="utf-8")
    pd = ENFORCED_POLLUTION_DEGREE if pollution_degree is None else pollution_degree
    try:
        return _tdb.resolve_insulation_declaration(text, pd)
    except ValueError as exc:
        where = DECLARATION_PATH if path is None else path
        raise InsulationDeclarationError(f"{where}: {exc}") from exc


@lru_cache(maxsize=1)
def _resolution() -> Any:
    """The production resolution, cached.

    Cached because it is read at import time by several modules and the
    declaration cannot change within a process; the cache is keyed on nothing
    because the path is fixed -- pass an explicit path to
    :func:`resolve_declaration` for any other file (tests do exactly that, and
    are therefore uncached).
    """
    return resolve_declaration()


def requirement_for_nets(net_a: str, net_b: str) -> Any:
    """The resolved pairing for two **net** names, in either order.

    Raises :class:`InsulationDeclarationError` when either net is not
    declared. That is deliberate and is the fail-closed direction: an
    undeclared net has no requirement, and returning ``None`` would invite a
    caller to treat "no requirement" as "no constraint". The gate
    ``scripts/check_insulation_pairings.py`` proves the declared net set
    matches ``elec/domain_manifest.yaml`` exactly, so this raising on a real
    board net means the two manifests have drifted.
    """
    resolution = _resolution()
    pairing = resolution.pairing_for_nets(net_a, net_b)
    if pairing is None:
        missing = [n for n in (net_a, net_b) if resolution.group_of(n) is None]
        raise InsulationDeclarationError(
            f"no insulation pairing for nets {net_a!r} and {net_b!r}: "
            f"{missing!r} not declared in {DECLARATION_PATH}. Every net of "
            "elec/domain_manifest.yaml's HV and SELV domains must be declared "
            "in exactly one group; an undeclared net has no requirement and "
            "none is assumed."
        )
    return pairing


@dataclass(frozen=True)
class NetClassRequirement:
    """The conservative reduction of a set of net pairings onto one
    net-class pair.

    Net class is a COARSER partition than the insulation grouping -- e.g.
    ``TEMPER_NET_ASSIGNMENTS`` puts ``PWR_RTN`` (mains-referenced, 120 V) and
    ``+170V_BUS`` (170 V d.c.) both in ``HighVoltage``, and puts ``tank-out``
    (570.5 V r.m.s.) there too while ``tank.c_tank1-p2`` goes to
    ``HighVoltageTank``. A rule that can only see net classes (KiCad's DRU
    language has no notion of safety domain) must therefore take the WORST
    member pairing, never an average and never a representative.

    ``determinable`` is ``False`` if **any** member pairing is
    indeterminate -- an indeterminacy cannot be diluted by pairing it with
    determinable neighbours.
    """

    class_a: str
    class_b: str
    floor_mm: float
    determinable: bool
    """``True`` only when every member pairing has a determinable
    requirement. When ``False``, ``floor_mm`` is a proven lower bound and
    clearing it is **not** compliance."""
    governing_pairing: str
    """The pairing key that set ``floor_mm``, e.g. ``"SELV<->TANK"``."""
    member_pairings: tuple[str, ...]
    """Every distinct pairing key this class pair reduces over, sorted."""

    @property
    def requirement_mm(self) -> float:
        """The requirement in mm, or ``nan`` when not determinable."""
        return self.floor_mm if self.determinable else float("nan")


def requirement_for_net_classes(
    class_a: str,
    class_b: str,
    net_to_class: dict[str, str],
) -> NetClassRequirement | None:
    """Reduce every declared pairing between two net classes onto one figure.

    *net_to_class* maps net name -> net class; pass
    ``temper_placer.core.design_rules.TEMPER_NET_ASSIGNMENTS``. Nets absent
    from it are skipped, and nets absent from the *declaration* are skipped --
    both are reported by ``scripts/check_insulation_pairings.py`` rather than
    silently absorbed here, because this function's job is the reduction, not
    the completeness proof.

    Returns ``None`` when the two classes have no declared net pair at all
    (e.g. two SELV-only classes whose nets are all undeclared). ``None`` means
    "this reduction has no members", **not** "no requirement": callers that
    emit rules must decide explicitly what to do with it, and the caller in
    ``scripts/generate_kicad_dru.py`` refuses to emit a rule rather than
    emitting a zero.

    The reduction is a ``max`` over floors, and ``all`` over determinability.
    It is conservative by construction: no member pairing can end up with a
    lower figure than its own.
    """
    resolution = _resolution()
    nets_a = [n for n, c in net_to_class.items() if c == class_a]
    nets_b = [n for n, c in net_to_class.items() if c == class_b]

    best: float = float("-inf")
    determinable = True
    governing = ""
    members: set[str] = set()
    for na in nets_a:
        for nb in nets_b:
            if na == nb:
                continue
            pairing = resolution.pairing_for_nets(na, nb)
            if pairing is None:
                continue
            members.add(pairing.key())
            determinable = determinable and pairing.is_determinable()
            floor = pairing.enforceable_floor_mm()
            if floor > best:
                best = floor
                governing = pairing.key()

    if not members:
        return None
    return NetClassRequirement(
        class_a=class_a,
        class_b=class_b,
        floor_mm=best,
        determinable=determinable,
        governing_pairing=governing,
        member_pairings=tuple(sorted(members)),
    )


def net_domain(net: str) -> str | None:
    """``"HV"``, ``"SELV"``, or ``None`` when *net* is not declared.

    The net-exact replacement for this repo's several hardcoded "is this net
    HV" classifiers. ``None`` means *undeclared*, which is deliberately NOT
    the same as "SELV": a caller that treats ``None`` as SELV would silently
    grant an unknown net the smallest requirement on the board. Callers must
    branch on ``None`` explicitly.
    """
    resolution = _resolution()
    group = resolution.group_of(net)
    if group is None:
        return None
    return _group_domain(group)


def requirement_for_class_to_domain(
    class_a: str,
    domain: str,
    net_to_class: dict[str, str],
) -> NetClassRequirement | None:
    """The conservative requirement between one net class and a whole domain.

    This is the shape a KiCad DRU ``"<HV class> to LV"`` rule needs: its
    condition is ``A.NetClass == X && B.NetClass != <every HV-family class>``,
    so its B side is *the entire SELV domain*, not one class. Reducing over
    one class pair at a time and taking the max by hand would be the same
    computation with an extra chance to forget a class.

    Same conservatism as :func:`requirement_for_net_classes`: ``max`` over
    floors, ``all`` over determinability. Returns ``None`` when *class_a* has
    no declared net (the caller must then decide explicitly; the DRU emitter
    refuses to emit a rule rather than emitting a zero).
    """
    resolution = _resolution()
    nets_a = [n for n, c in net_to_class.items() if c == class_a]
    nets_b = [
        n for n, g in resolution.declared_nets().items() if _group_domain(g) == domain
    ]

    best: float = float("-inf")
    determinable = True
    governing = ""
    members: set[str] = set()
    for na in nets_a:
        for nb in nets_b:
            if na == nb:
                continue
            pairing = resolution.pairing_for_nets(na, nb)
            if pairing is None:
                continue
            members.add(pairing.key())
            determinable = determinable and pairing.is_determinable()
            floor = pairing.enforceable_floor_mm()
            if floor > best:
                best = floor
                governing = pairing.key()

    if not members:
        return None
    return NetClassRequirement(
        class_a=class_a,
        class_b=f"<domain {domain}>",
        floor_mm=best,
        determinable=determinable,
        governing_pairing=governing,
        member_pairings=tuple(sorted(members)),
    )


@lru_cache(maxsize=1)
def _group_domains() -> dict[str, str]:
    """group name -> ``"HV"`` / ``"SELV"``.

    Read back off the resolved pairings rather than re-parsing the YAML: the
    domain of a group is already carried on every pairing it participates in,
    and re-parsing would be a second reader of the same declaration.
    """
    out: dict[str, str] = {}
    for pairing in _resolution().pairings():
        out[pairing.group_a()] = pairing.domain_a()
        out[pairing.group_b()] = pairing.domain_b()
    return out


def _group_domain(group: str) -> str:
    return _group_domains()[group]


def barrier_floor_mm() -> float:
    """The worst enforceable floor over every barrier-crossing pairing.

    This is the figure a single, geometric, whole-board HV<->SELV barrier must
    be sized by. One physical barrier separates the *whole* HV domain from the
    *whole* SELV domain, so it is governed by its worst crossing -- see
    ``docs/evidence/2026-08-19-table-17-row-determination-hv-selv.md`` §6.1:
    *"They are the same physical barrier as rows 3 and 4 and are governed by
    whichever pairing is worst."*
    """
    return float(_resolution().barrier_floor_mm())


def barrier_is_determinable() -> bool:
    """``False`` when any barrier-crossing pairing is indeterminate.

    Barrier compliance cannot be asserted while this is ``False``, no matter
    how wide the barrier is. It is ``False`` today: the tank crossings switch
    at 47 kHz.
    """
    return bool(_resolution().barrier_is_determinable())


def limitation() -> str:
    """The honest limit on what any of this proves.

    Sourced from the Rust constant so the sentence has exactly one home and
    cannot drift between the declaration, the gate and this module.
    """
    return _tdb.insulation_mechanism_limitation()
