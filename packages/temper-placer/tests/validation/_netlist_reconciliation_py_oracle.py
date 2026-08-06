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
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
# Self-contained S-expression parser for the compiled design netlist
# (deliberate copy of the parser convention in scripts/check_domain_partition
# .py et al. -- see module docstring).
# ---------------------------------------------------------------------------

_TOKEN = re.compile(r'\s*(?:(\()|(\))|("(?:\\.|[^"\\])*")|([^\s()]+))', re.S)


def _sexp(text: str) -> list[Any]:
    tokens: list[str] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if not match:
            if text[pos:].strip():
                raise ReconciliationGateError(f"invalid netlist syntax at byte {pos}")
            break
        pos = match.end()
        tokens.append(match.group(1) or match.group(2) or match.group(3) or match.group(4))
    root: list[Any] = []
    stack: list[list[Any]] = [root]
    for token in tokens:
        if token == "(":
            node: list[Any] = []
            stack[-1].append(node)
            stack.append(node)
        elif token == ")":
            if len(stack) == 1:
                raise ReconciliationGateError("unbalanced netlist: unmatched ')'")
            stack.pop()
        else:
            stack[-1].append(json.loads(token) if token.startswith('"') else token)
    if len(stack) != 1:
        raise ReconciliationGateError("unbalanced netlist: unmatched '('")
    return root


def _children(node: list[Any], name: str) -> list[list[Any]]:
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


def _field(node: list[Any], name: str, *, required: bool = True) -> str:
    fields = _children(node, name)
    if len(fields) > 1 or (required and not fields):
        raise ReconciliationGateError(f"invalid {name!r} field in {node[0]!r}")
    if not fields:
        return ""
    if len(fields[0]) != 2 or not isinstance(fields[0][1], str):
        raise ReconciliationGateError(f"malformed {name!r} field in {node[0]!r}")
    return fields[0][1]


def _instance_path_from_sheetpath(sheetpath_node: list[Any]) -> str:
    """Extract the dotted atopile instance path (e.g. 'aux_supply.psu') from
    a sheetpath's ``names`` field ('.../main.ato:Top::aux_supply.psu'),
    stable across machines (the absolute path prefix before '::' is
    discarded) and across ref-designator reshuffles. Same normalisation as
    ``scripts/check_domain_partition.py`` and ``gen_pcb_skeleton.py``."""
    for child in _children(sheetpath_node, "names"):
        names = child[1] if len(child) > 1 and isinstance(child[1], str) else ""
        if "::" in names:
            return names.split("::", 1)[1]
    return ""


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
    """
    netlist_path = Path(path)
    if not netlist_path.is_file():
        raise ReconciliationGateError(f"netlist not found: {netlist_path}")
    text = netlist_path.read_text(encoding="utf-8")
    if not text.strip():
        raise ReconciliationGateError(f"netlist file is empty: {netlist_path}")
    parsed = _sexp(text)
    export = next(
        (item for item in parsed if isinstance(item, list) and item[:1] == ["export"]), None
    )
    if export is None:
        raise ReconciliationGateError(f"netlist has no 'export' block: {netlist_path}")

    components_block = _children(export, "components")
    if len(components_block) != 1:
        raise ReconciliationGateError("netlist must contain exactly one 'components' block")

    components: list[DesignComponent] = []
    duplicate_refs: list[tuple[str, str, str]] = []
    seen_paths: dict[str, str] = {}
    ref_paths: dict[str, str] = {}
    for node in _children(components_block[0], "comp"):
        ref = _field(node, "ref")
        sheetpath_nodes = _children(node, "sheetpath")
        instance_path = (
            _instance_path_from_sheetpath(sheetpath_nodes[0]) if sheetpath_nodes else ""
        )
        if not instance_path:
            raise ReconciliationGateError(
                f"design component {ref!r} has no usable 'sheetpath' field -- "
                "cannot establish a designator-renumbering-safe identity for it"
            )
        if instance_path in seen_paths:
            raise ReconciliationGateError(
                f"design netlist has two components sharing instance path "
                f"{instance_path!r} ({seen_paths[instance_path]!r} and {ref!r}) "
                "-- identity is ambiguous, refusing to guess"
            )
        seen_paths[instance_path] = ref
        if ref in ref_paths:
            duplicate_refs.append((ref, ref_paths[ref], instance_path))
        else:
            ref_paths[ref] = instance_path
        components.append(DesignComponent(ref=ref, instance_path=instance_path))

    if not components:
        raise ReconciliationGateError(f"netlist contains zero components: {netlist_path}")

    nets_block = _children(export, "nets")
    if len(nets_block) != 1:
        raise ReconciliationGateError("netlist must contain exactly one 'nets' block")

    nets: dict[str, list[tuple[str, str]]] = {}
    pin_owner: dict[tuple[str, str], str] = {}
    for node in _children(nets_block[0], "net"):
        name = _field(node, "name")
        if name in nets:
            raise ReconciliationGateError(f"duplicate net name in netlist: {name!r}")
        nodelist: list[tuple[str, str]] = []
        for nn in _children(node, "node"):
            ref = _field(nn, "ref")
            pin = _field(nn, "pin")
            if (ref, pin) in pin_owner:
                raise ReconciliationGateError(
                    f"pin {ref}.{pin} appears in more than one net "
                    f"({pin_owner[(ref, pin)]!r} and {name!r}) -- malformed netlist"
                )
            pin_owner[(ref, pin)] = name
            nodelist.append((ref, pin))
        nets[name] = nodelist

    if not nets:
        raise ReconciliationGateError(f"netlist contains zero nets: {netlist_path}")

    return DesignNetlist(components=components, nets=nets, duplicate_refs=duplicate_refs)


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


def _component_findings(board: BoardNetlist, design: DesignNetlist) -> list[ReconciliationFinding]:
    findings: list[ReconciliationFinding] = []

    # UNKEYABLE: board footprints without a Sheetpath -- reported, never
    # silently dropped, never matched by guess.
    for comp in board.components:
        if not comp.sheetpath:
            findings.append(
                ReconciliationFinding(
                    kind=KIND_UNKEYABLE,
                    severity=SEVERITY_ERROR,
                    detail=(
                        f"{comp.ref}: board footprint has no 'Sheetpath' property -- "
                        "cannot be identity-matched against the netlist at all"
                    ),
                    refs=(comp.ref,),
                )
            )

    design_by_path: dict[str, str] = {
        comp.instance_path: comp.ref for comp in design.components
    }
    board_by_path: dict[str, str] = {comp.sheetpath: comp.ref for comp in board.components}

    # REUSE on the board side: two board footprints sharing a ref.
    board_ref_paths: dict[str, list[str]] = {}
    for comp in board.components:
        board_ref_paths.setdefault(comp.ref, []).append(comp.sheetpath)
    for ref, paths in sorted(board_ref_paths.items()):
        if len(paths) > 1:
            findings.append(
                ReconciliationFinding(
                    kind=KIND_REUSE,
                    severity=SEVERITY_ERROR,
                    detail=(
                        f"ref {ref!r} names {len(paths)} board components "
                        f"({', '.join(p or '<no sheetpath>' for p in paths)}) -- "
                        "one ref, multiple components"
                    ),
                    refs=(ref,),
                    paths=tuple(paths),
                )
            )

    # REUSE on the design side: two netlist components sharing a ref (the R39
    # reused-refdes mutation's owning finding -- the mutation is applied to
    # the design netlist, so the check must fire on the design side too).
    for ref, path_a, path_b in design.duplicate_refs:
        findings.append(
            ReconciliationFinding(
                kind=KIND_REUSE,
                severity=SEVERITY_ERROR,
                detail=(
                    f"ref {ref!r} names two design components "
                    f"({path_a!r} and {path_b!r}) -- one ref, multiple components"
                ),
                refs=(ref,),
                paths=(path_a, path_b),
            )
        )

    # MISSING / RENUMBERED / EXTRA, keyed by instance path.
    matched = 0
    for path in sorted(design_by_path):
        design_ref = design_by_path[path]
        board_ref = board_by_path.get(path)
        if board_ref is None:
            findings.append(
                ReconciliationFinding(
                    kind=KIND_MISSING,
                    severity=SEVERITY_ERROR,
                    detail=(
                        f"design component {design_ref!r} (path {path!r}) has no "
                        "board footprint carrying this sheetpath -- the board has "
                        "never been resynced to include this component (the "
                        "tank-capacitor class)"
                    ),
                    refs=(design_ref,),
                    paths=(path,),
                )
            )
        else:
            matched += 1
            if design_ref != board_ref:
                findings.append(
                    ReconciliationFinding(
                        kind=KIND_RENUMBERED,
                        severity=SEVERITY_ERROR,
                        detail=(
                            f"path {path!r} carries different refs: design "
                            f"{design_ref!r} vs board {board_ref!r} -- a "
                            "designator renumber (refdes overlap is blind to "
                            "this class)"
                        ),
                        refs=(design_ref, board_ref),
                        paths=(path,),
                    )
                )

    for path in sorted(board_by_path):
        if path not in design_by_path:
            findings.append(
                ReconciliationFinding(
                    kind=KIND_EXTRA,
                    severity=SEVERITY_ERROR,
                    detail=(
                        f"board footprint {board_by_path[path]!r} (path {path!r}) "
                        "has no matching component in the compiled netlist -- "
                        "stale board, or a corrupted Sheetpath property"
                    ),
                    refs=(board_by_path[path],),
                    paths=(path,),
                )
            )

    return findings


def _net_findings(
    board: BoardNetlist, design_net_paths: dict[str, set[str]]
) -> list[ReconciliationFinding]:
    """Net-level membership reconciliation.

    NET-MISSING / NET-MEMBERSHIP are driven by the DESIGN net set; NET-EXTRA
    by the board side. A declared-but-empty design net with no board
    counterpart is deliberately NOT a finding: the real compiled netlist
    declares nets with zero nodes (e.g. ``gnd_ref``) that legitimately have
    no board presence -- reporting them would manufacture findings on a clean
    pair. The same net WITH a non-empty board counterpart is the dropped-net
    signature (design side emptied, board side intact) and fires
    NET-MEMBERSHIP.
    """
    findings: list[ReconciliationFinding] = []

    for name, paths in sorted(design_net_paths.items()):
        board_paths = board.nets.get(name)
        if not paths:
            # Declared-but-empty design net. No board counterpart -> nothing
            # to compare (legitimately unused on both sides); board
            # counterpart -> the dropped-net signature: design side emptied,
            # board side intact.
            if board_paths:
                findings.append(
                    ReconciliationFinding(
                        kind=KIND_NET_MEMBERSHIP,
                        severity=SEVERITY_ERROR,
                        detail=(
                            f"net {name!r} connects board component(s) "
                            f"{', '.join(sorted(board_paths))} but has zero "
                            "nodes in the compiled netlist -- the net's "
                            "membership was dropped on the design side "
                            "(dropped-net class)"
                        ),
                        paths=tuple(sorted(board_paths)),
                    )
                )
            continue
        if board_paths is None:
            findings.append(
                ReconciliationFinding(
                    kind=KIND_NET_MISSING,
                    severity=SEVERITY_ERROR,
                    detail=(
                        f"net {name!r} connects design component(s) "
                        f"{', '.join(sorted(paths))} but has no counterpart on "
                        "the board -- a design net with zero placed components"
                    ),
                    paths=tuple(sorted(paths)),
                )
            )
        elif board_paths != paths:
            findings.append(
                ReconciliationFinding(
                    kind=KIND_NET_MEMBERSHIP,
                    severity=SEVERITY_ERROR,
                    detail=_net_membership_detail(name, paths, board_paths),
                    paths=tuple(sorted(paths ^ board_paths)),
                )
            )

    for name, board_paths in sorted(board.nets.items()):
        if name not in design_net_paths:
            findings.append(
                ReconciliationFinding(
                    kind=KIND_NET_EXTRA,
                    severity=SEVERITY_ERROR,
                    detail=(
                        f"net {name!r} connects board component(s) "
                        f"{', '.join(sorted(board_paths))} but does not exist in "
                        "the compiled netlist -- stale board or orphaned "
                        "assignment"
                    ),
                    paths=tuple(sorted(board_paths)),
                )
            )

    return findings


def _net_membership_detail(name: str, design_paths: set[str], board_paths: set[str]) -> str:
    only_design = sorted(design_paths - board_paths)
    only_board = sorted(board_paths - design_paths)
    parts = [f"net {name!r} has different component membership between the two sides"]
    if only_design:
        parts.append(f"design-only: {', '.join(only_design)}")
    if only_board:
        parts.append(f"board-only: {', '.join(only_board)}")
    return " -- ".join(parts)


def _resolve_design_net_paths(design: DesignNetlist) -> dict[str, set[str]]:
    """Design net name -> set of instance paths it connects. A node touching a
    duplicated ref contributes every candidate path -- inherently ambiguous,
    and REUSE is that corruption's owning finding.

    NOTE: nets that resolve to an EMPTY path set are kept in the mapping (as
    empty sets), not dropped. An empty set is the signature of the R39
    dropped-net mutation (the net stays declared, its nodes are removed): it
    must be distinguishable from a net that was never declared at all so the
    reconciliation can report NET-MEMBERSHIP (design empty vs board non-empty)
    rather than misreading the emptied net as a board-only NET-EXTRA."""
    design_ref_to_paths = design.ref_to_paths
    out: dict[str, set[str]] = {}
    for name, nodes in design.nets.items():
        paths: set[str] = set()
        for ref, _pin in nodes:
            paths.update(design_ref_to_paths.get(ref, []))
        out[name] = paths
    return out


def reconcile(board: BoardNetlist, design: DesignNetlist) -> ReconciliationReport:
    """Compare the board-side and design-side netlists, returning every
    finding keyed by instance path and net membership (never by refdes
    overlap)."""
    design_net_paths = _resolve_design_net_paths(design)
    return ReconciliationReport(
        findings=_component_findings(board, design)
        + _net_findings(board, design_net_paths),
        design_components=len(design.components),
        board_components=len(board.components),
        matched_paths=sum(
            1
            for path in {c.instance_path for c in design.components}
            if path in {c.sheetpath for c in board.components}
        ),
        design_nets_nonempty=sum(1 for paths in design_net_paths.values() if paths),
        board_nets=len(board.nets),
    )
