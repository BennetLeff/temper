"""Netlist <-> board reconciliation oracle (plan 2026-08-02-021, R16/R39).

Compares the netlist extracted from the actual board file
(``pcb/temper.kicad_pcb``) against the compiled design netlist
(``elec/build/default.net``) keyed by instance path and net membership --
NOT by reference designator. Component identity stops being a refdes-set
overlap guess and becomes a per-component and per-net reconciliation.

Why not refdes (the handoff lesson, docs/handoffs/2026-07-31-ci-enforcement-
and-board-defects.md): refdes is positional and reusable. A wholesale renumber
is a permutation of the same refdes set, so any set-overlap check
(``preflight_identity``'s 95% threshold) passes it by construction; and a
reused designator is invisible to set comparison entirely -- on the current
board, board ``C27`` names ``tank.c_tank3`` (Sheetpath property) while the
design netlist's ``C27`` used to name a different component
(``ct_sense.c_filter``): one ref, two components. The stable identity is the
dotted atopile module-instantiation path (``tank.c_tank3``), the same key
``resync_pcb_netlist.py`` and ``check_footprint_drift.py`` already match on.

Finding taxonomy (each class has its own owning finding -- the explicit
design requirement, so wholesale renumbering, missing components, and the
tank-capacitor class fail regardless of refdes overlap):

Component level (keyed by instance path):
  - MISSING:   design path with no board footprint carrying it (the
               tank-capacitor class -- on the CURRENT board this is
               PASS-for-missing: ``tank.c_tank3`` IS in the board file,
               staged off-outline; the off-board staging is a containment
               defect owned by the R26 plan, not this reconciliation).
  - EXTRA:     board footprint path with no design counterpart (stale board).
  - RENUMBERED: same path on both sides, different refs (wholesale renumber).
  - REUSE:     two components sharing one ref, on EITHER side (refdes reuse;
               detected on the design side too, so the injected reuse
               mutation of R39 has an owning check on the netlist it is
               actually applied to).
  - UNKEYABLE: board footprint with no Sheetpath property -- reported, never
               silently dropped or matched by guess.

Net level (keyed by net name; node sets compared at COMPONENT membership):
  - NET-MISSING:    design net (non-empty) with no board counterpart.
  - NET-EXTRA:      board net (non-empty) with no design counterpart
                    (fail-closed direction: a board-side net is never
                    silently dropped).
  - NET-MEMBERSHIP: net present on both sides whose component node sets
                    differ (the owning finding of the dropped-net class of
                    R39: a dropped net's design-side node set becomes empty
                    while the board's stays non-empty).

Net node sets are compared at the component (sheetpath) level, not the pin
level, because pad-numbering conventions legitimately differ between the two
sides for parts like the relay (board pads A1/A2/13/14 vs netlist pins
1/2/3/4, resolved positionally by ``resync_pcb_netlist.py``): a pin-level
comparison would manufacture NET-MEMBERSHIP findings for identical
connectivity. What the dropped-net class actually changes -- which components
are connected together -- is fully visible at the component level.

The parser below is a DELIBERATE copy of the equivalent self-contained
s-expression parser in ``scripts/check_footprint_drift.py`` /
``scripts/check_copper_net_consistency.py`` / ``scripts/check_domain_partition
.py`` (same convention those gates document): this oracle's correctness must
not depend on a gate/generator script's internal representation changing out
from under it. The one deliberate difference from the strict parsers: the
design-side parser tolerates duplicate component refs (recording them as
REUSE candidates) so the R39 reused-refdes mutation -- a netlist that strict
parsers reject outright -- can be loaded and reconciled, which is what lets
the corpus prove the REUSE finding bites.

Wave 4 Phase 4: the self-contained s-expression parser (``_sexp``), the
design-netlist parse navigation (``_field``/``_children``/
``_instance_path_from_sheetpath`` and the strict fail-closed checks), and
the reconciliation decision logic (``_component_findings``/
``_net_findings``/``_resolve_design_net_paths``/``reconcile``) are
implemented in Rust as the ``validation`` submodule of
``temper_design_bundle_python`` (``temper-design-bundle/src/validation.rs``)
and delegated to here. This module keeps the dataclasses
(``BoardNetlist``/``DesignNetlist``/``ReconciliationFinding``/
``ReconciliationReport``/``ReconciliationGateError``), the file I/O
(``extract_board_netlist``'s ``parse_kicad_pcb_v6`` call,
``parse_design_netlist``'s file read), and the board-side traversal
(``build_board_netlist`` reads the Component contract pyclass attributes).
Every error string raised by the parser/parse/reconcile is byte-identical
(they are plain str / ``!r`` interpolations -- no no-format float repr),
and the shim re-wraps the kernel's ``PyValueError`` into
``ReconciliationGateError`` with ``from None`` (the oracle raises the gate
error directly, so ``__cause__`` is None on both sides).

Verification: bit-identical parity against the pinned pre-migration
implementation is asserted by
``tests/validation/test_netlist_reconciliation_rust_differential.py``
(oracle: ``tests/validation/_netlist_reconciliation_py_oracle.py``); the
structural proof lives in ``packages/temper-design-bundle/VERIFICATION.md``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import temper_design_bundle_python as _tdb

from temper_placer.core.netlist import Component

__all__ = [
    "BoardNetlist",
    "DesignComponent",
    "DesignNetlist",
    "ReconciliationFinding",
    "ReconciliationGateError",
    "ReconciliationReport",
    "build_board_netlist",
    "extract_board_netlist",
    "parse_design_netlist",
    "reconcile",
    # The finding-taxonomy / mutation-class-to-check constants are public
    # API (the R16 plan's class-to-check table) and are re-exported so they
    # survive the migration to Rust delegation.
    "KIND_MISSING",
    "KIND_EXTRA",
    "KIND_RENUMBERED",
    "KIND_REUSE",
    "KIND_UNKEYABLE",
    "KIND_NET_MISSING",
    "KIND_NET_EXTRA",
    "KIND_NET_MEMBERSHIP",
    "SEVERITY_ERROR",
    "MUTATION_OWNING_KINDS",
]

# Finding kinds (machine-readable).
KIND_MISSING = "MISSING"
KIND_EXTRA = "EXTRA"
KIND_RENUMBERED = "RENUMBERED"
KIND_REUSE = "REUSE"
KIND_UNKEYABLE = "UNKEYABLE"
KIND_NET_MISSING = "NET-MISSING"
KIND_NET_EXTRA = "NET-EXTRA"
KIND_NET_MEMBERSHIP = "NET-MEMBERSHIP"

# Every reconciliation finding fails the gate; kept as a field so a future
# severity ladder (INFO/WARNING for advisory classes) can be added without a
# breaking shape change.
SEVERITY_ERROR = "ERROR"

#: Finding kinds that own the R39 mutation classes (class-to-check table used
#: by the corpus runner and its tests).
MUTATION_OWNING_KINDS = {
    "renumber": KIND_RENUMBERED,
    "dropped-net": KIND_NET_MEMBERSHIP,
    "reused-refdes": KIND_REUSE,
}


class ReconciliationGateError(Exception):
    """Fail-closed condition: the reconciliation could not run a trustworthy
    comparison (missing/malformed input, zero components, duplicate instance
    paths, an un-keyable design component). Never reported as '0 findings'."""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DesignComponent:
    """A single design-netlist component. ``ref`` is NOT guaranteed unique
    across the list: a reused-refdes mutation legitimately produces two
    components sharing one ref, and this representation must hold it so the
    REUSE finding has something to fire on (the strict netlist parsers reject
    such a netlist outright, which is exactly why the mutation corpus cannot
    use them as its comparison authority)."""

    ref: str
    instance_path: str


@dataclass
class DesignNetlist:
    components: list[DesignComponent]
    nets: dict[str, list[tuple[str, str]]]  # net name -> [(ref, pin), ...]
    duplicate_refs: list[tuple[str, str, str]] = field(default_factory=list)  # (ref, path_a, path_b)

    @property
    def ref_to_paths(self) -> dict[str, list[str]]:
        """ref -> list of instance paths carrying it (len > 1 exactly for the
        reused-refdes corruption; net nodes referencing such a ref cannot be
        unambiguously attributed to one path, which is inherent to the
        corruption and acceptable -- the REUSE finding is the owning check)."""
        out: dict[str, list[str]] = {}
        for comp in self.components:
            out.setdefault(comp.ref, []).append(comp.instance_path)
        return out


@dataclass(frozen=True)
class BoardComponent:
    ref: str
    sheetpath: str


@dataclass
class BoardNetlist:
    components: list[BoardComponent]
    nets: dict[str, set[str]]  # net name -> set of sheetpaths connected


@dataclass(frozen=True)
class ReconciliationFinding:
    kind: str
    severity: str
    detail: str
    refs: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()


@dataclass
class ReconciliationReport:
    findings: list[ReconciliationFinding] = field(default_factory=list)
    design_components: int = 0
    board_components: int = 0
    matched_paths: int = 0
    design_nets_nonempty: int = 0
    board_nets: int = 0

    @property
    def passed(self) -> bool:
        return not self.findings

    def findings_of(self, kind: str) -> list[ReconciliationFinding]:
        return [f for f in self.findings if f.kind == kind]


# ---------------------------------------------------------------------------
# Board-side extraction
# ---------------------------------------------------------------------------


def build_board_netlist(components: Iterable[Component]) -> BoardNetlist:
    """Build the board-side netlist from the parsed board model's components
    (``ParsedPCB.components`` -- ``temper_placer.core.netlist.Component``
    instances whose ``sheetpath`` comes from each footprint's ``Sheetpath``
    property and whose pins carry the pad net assignments).

    Every footprint resolves a ref (components with no ref are already
    skipped by the parser); a footprint with no Sheetpath is carried through
    as an UNKEYABLE candidate (``sheetpath`` is None) -- the reconciliation
    reports it, never guesses.
    """
    board_components: list[BoardComponent] = []
    nets: dict[str, set[str]] = {}
    for comp in components:
        board_components.append(
            BoardComponent(ref=comp.ref, sheetpath=comp.sheetpath or "")
        )
        for pin in comp.pins:
            if not pin.net:
                continue
            nets.setdefault(pin.net, set()).add(comp.sheetpath or "")
    return BoardNetlist(components=board_components, nets=nets)


def extract_board_netlist(pcb_path: Path | str) -> BoardNetlist:
    """Parse ``pcb_path`` (a ``.kicad_pcb``) and build the board-side netlist.

    Uses ``parse_kicad_pcb_v6`` so the board-side extraction is exactly the
    parsed board model the rest of the pipeline consumes.
    """
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6

    if not Path(pcb_path).is_file():
        raise ReconciliationGateError(f"board not found: {pcb_path}")
    parsed = parse_kicad_pcb_v6(Path(pcb_path))
    if not parsed.components:
        raise ReconciliationGateError(f"board has zero footprints: {pcb_path}")
    return build_board_netlist(parsed.components)


# ---------------------------------------------------------------------------
# Design-side parsing
# ---------------------------------------------------------------------------


def parse_design_netlist(path: Path | str) -> DesignNetlist:
    """Parse the compiled design netlist (``elec/build/default.net``) into the
    reconciliation's comparison shape.

    Tolerates duplicate component refs (recording them as REUSE candidates)
    so the R39 reused-refdes mutation can be loaded and proven to bite -- see
    the module docstring. Everything else is strict and fail-closed: a design
    component with no usable sheetpath cannot be identity-matched at all.

    The self-contained s-expression parser and the strict fail-closed checks
    are the ``parse_design_netlist`` kernel in
    ``temper_design_bundle_python.validation`` (Rust); the file read and the
    not-found/empty checks stay here (I/O boundary), and the kernel's
    ``PyValueError`` (byte-identical message) is re-wrapped into
    ``ReconciliationGateError`` with ``from None`` -- the oracle raises the
    gate error directly, so ``__cause__`` is None on both sides.
    """
    netlist_path = Path(path)
    if not netlist_path.is_file():
        raise ReconciliationGateError(f"netlist not found: {netlist_path}")
    text = netlist_path.read_text(encoding="utf-8")
    if not text.strip():
        raise ReconciliationGateError(f"netlist file is empty: {netlist_path}")

    try:
        components, nets, duplicate_refs = _tdb.validation.parse_design_netlist(
            str(netlist_path), text
        )
    except ValueError as exc:
        raise ReconciliationGateError(str(exc)) from None

    return DesignNetlist(
        components=[DesignComponent(ref=ref, instance_path=path_) for ref, path_ in components],
        nets={name: list(nodes) for name, nodes in nets},
        duplicate_refs=[(ref, path_a, path_b) for ref, path_a, path_b in duplicate_refs],
    )


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


def reconcile(board: BoardNetlist, design: DesignNetlist) -> ReconciliationReport:
    """Compare the board-side and design-side netlists, returning every
    finding keyed by instance path and net membership (never by refdes
    overlap).

    The comparison compute — the component-level findings (UNKEYABLE /
    REUSE / MISSING / RENUMBERED / EXTRA), the net-path resolution and
    net-level findings (NET-MISSING / NET-EXTRA / NET-MEMBERSHIP), and the
    report counters — is the ``reconcile`` kernel in
    ``temper_design_bundle_python.validation`` (Rust). The board-side
    traversal (``build_board_netlist``) and the dataclass wrapping stay
    here. Board net node sets are passed as unordered lists; the kernel
    compares them as sets, exactly as the oracle's `set != set` does.
    """
    findings, design_components, board_components, matched_paths, design_nets_nonempty, board_nets = (
        _tdb.validation.reconcile(
            [(c.ref, c.sheetpath) for c in board.components],
            [(name, sorted(paths)) for name, paths in board.nets.items()],
            [(c.ref, c.instance_path) for c in design.components],
            [(name, list(nodes)) for name, nodes in design.nets.items()],
            list(design.duplicate_refs),
        )
    )
    return ReconciliationReport(
        findings=[
            ReconciliationFinding(
                kind=f["kind"],
                severity=f["severity"],
                detail=f["detail"],
                refs=tuple(f["refs"]),
                paths=tuple(f["paths"]),
            )
            for f in findings
        ],
        design_components=design_components,
        board_components=board_components,
        matched_paths=matched_paths,
        design_nets_nonempty=design_nets_nonempty,
        board_nets=board_nets,
    )
