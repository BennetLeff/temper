#!/usr/bin/env python3
"""Netlist domain-partition gate: verify galvanic isolation is real.

Reads the *compiled* netlist (elec/build/default.net, produced by
`make netlist`) and a hand-reviewed domain manifest (elec/domain_manifest.yaml)
that declares which nets belong to the HV/mains domain, which belong to the
SELV/control domain, and which components are legitimate galvanic isolators
between them (with their pin groups). It then computes connected components
of the netlist graph -- treating every non-isolator component as fully
conductive across its own pins, and every declared isolator as conductive
only *within* its declared groups, never across them -- and asserts:

  1. no HV-domain net and SELV-domain net share a connected component, and
  2. no declared isolator's own groups share a connected component with
     each other (i.e. the isolator's own barrier is not bridged elsewhere
     in the network).

This exists because the netlist can be internally consistent, ERC-clean,
and BOM-reconciled while still shorting a 4.2kVAC isolation barrier -- which
is exactly what happened here (docs/hardware/IEC60335_CRITICAL_COMPONENTS.md
Sec 2, docs/STRATEGY.md "The isolation barrier is shorted by the star-point
join"). None of the existing checks compare claimed domain structure against
actual connectivity; this one does.

Reads the netlist, not the .ato source: the source is the claim, the
compiled netlist is what would actually get fabricated.

Fail-closed contract (METHODOLOGY.md Sec 4/5): this gate never exits 0
unless it positively confirms it ran a real check on real, fresh data.
It exits non-zero -- never silently 0 -- for every one of:
  - the netlist file is missing
  - the netlist is empty (0 components or 0 nets)
  - the netlist is STALE (older than any elec/src/*.ato file) -- a stale
    netlist silently checking yesterday's design is indistinguishable from
    "no violations" and is the single most common way this class of gate
    has died on this project
  - the manifest file is missing, empty, or malformed
  - a domain has zero nets, or a net is declared under more than one domain
  - a declared domain net does not exist anywhere in the netlist (typo/stale)
  - a declared isolator's instance_path matches no component (the isolator
    the model depends on may have been removed from the design)
  - a declared isolator's pin groups do not exactly partition every pin
    that component actually has wired (missing or duplicated pin coverage)

Exit codes:
  0 - PASSED: manifest and netlist both loaded and validated, 0 violations
  3 - VIOLATION: a real domain crossing or isolator-barrier breach was found
  5 - GATE ERROR: the gate could not run a trustworthy check at all (see
      list above) -- never treated as "0 violations"

Usage:
  uv run python scripts/check_domain_partition.py
  uv run python scripts/check_domain_partition.py --netlist PATH --manifest PATH
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.repo import find_repo_root
from _lib.github_summary import get_github_summary_path

REPO_ROOT = find_repo_root()
DEFAULT_NETLIST = REPO_ROOT / "elec" / "build" / "default.net"
DEFAULT_MANIFEST = REPO_ROOT / "elec" / "domain_manifest.yaml"
DEFAULT_SRC_DIR = REPO_ROOT / "elec" / "src"

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


# ---------------------------------------------------------------------------
# S-expression parser for the KiCad-format netlist (self-contained; mirrors
# the parser in scripts/gen_schematics.py, which reads the same file format).
# ---------------------------------------------------------------------------

import re as _re

_TOKEN = _re.compile(r'\s*(?:(\()|(\))|("(?:\\.|[^"\\])*")|([^\s()]+))', _re.S)


def _sexp(text: str) -> list[Any]:
    tokens: list[str] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if not match:
            if text[pos:].strip():
                raise GateError(f"invalid netlist syntax at byte {pos}")
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
                raise GateError("unbalanced netlist: unmatched ')'")
            stack.pop()
        else:
            stack[-1].append(json.loads(token) if token.startswith('"') else token)
    if len(stack) != 1:
        raise GateError("unbalanced netlist: unmatched '('")
    return root


def _children(node: list[Any], name: str) -> list[list[Any]]:
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


def _field(node: list[Any], name: str, *, required: bool = True) -> str:
    fields = _children(node, name)
    if len(fields) > 1 or (required and not fields):
        raise GateError(f"invalid {name!r} field in {node[0]!r}")
    if not fields:
        return ""
    if len(fields[0]) != 2 or not isinstance(fields[0][1], str):
        raise GateError(f"malformed {name!r} field in {node[0]!r}")
    return fields[0][1]


def _instance_path_from_sheetpath(sheetpath_node: list[Any]) -> str:
    """Extract the dotted atopile instance path, e.g. 'aux_supply.psu', from
    a sheetpath's `names` field ('.../main.ato:Top::aux_supply.psu'). This is
    stable across machines/worktrees (the absolute path prefix before '::'
    is discarded) and across ref-designator reshuffles."""
    for child in _children(sheetpath_node, "names"):
        names = child[1] if len(child) > 1 else ""
        if "::" in names:
            return names.split("::", 1)[1]
    return ""


@dataclass
class NetlistComponent:
    ref: str
    instance_path: str


@dataclass
class Netlist:
    components: dict[str, NetlistComponent]  # ref -> component
    nets: dict[str, str]  # code -> name
    net_nodes: dict[str, list[tuple[str, str]]]  # code -> [(ref, pin), ...]
    pin_net: dict[tuple[str, str], str]  # (ref, pin) -> net code
    ref_pins: dict[str, list[str]]  # ref -> [pin, ...] actually wired


def parse_netlist(path: Path) -> Netlist:
    if not path.is_file():
        raise GateError(f"netlist not found: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise GateError(f"netlist file is empty: {path}")
    parsed = _sexp(text)
    export = next(
        (item for item in parsed if isinstance(item, list) and item[:1] == ["export"]),
        None,
    )
    if export is None:
        raise GateError(f"netlist has no 'export' block: {path}")

    components_block = _children(export, "components")
    if len(components_block) != 1:
        raise GateError("netlist must contain exactly one 'components' block")
    components: dict[str, NetlistComponent] = {}
    for node in _children(components_block[0], "comp"):
        ref = _field(node, "ref")
        sheetpath_nodes = _children(node, "sheetpath")
        instance_path = ""
        if sheetpath_nodes:
            instance_path = _instance_path_from_sheetpath(sheetpath_nodes[0])
        if ref in components:
            raise GateError(f"duplicate component ref in netlist: {ref!r}")
        components[ref] = NetlistComponent(ref=ref, instance_path=instance_path)

    nets_block = _children(export, "nets")
    if len(nets_block) != 1:
        raise GateError("netlist must contain exactly one 'nets' block")
    nets: dict[str, str] = {}
    net_nodes: dict[str, list[tuple[str, str]]] = {}
    pin_net: dict[tuple[str, str], str] = {}
    ref_pins: dict[str, list[str]] = {}
    for node in _children(nets_block[0], "net"):
        code = _field(node, "code")
        name = _field(node, "name")
        if code in nets:
            raise GateError(f"duplicate net code in netlist: {code!r}")
        nets[code] = name
        nodelist: list[tuple[str, str]] = []
        for nn in _children(node, "node"):
            ref = _field(nn, "ref")
            pin = _field(nn, "pin")
            if (ref, pin) in pin_net:
                raise GateError(
                    f"pin {ref}.{pin} appears in more than one net "
                    f"({pin_net[(ref, pin)]!r} and {code!r}) -- malformed netlist"
                )
            pin_net[(ref, pin)] = code
            nodelist.append((ref, pin))
            ref_pins.setdefault(ref, []).append(pin)
        net_nodes[code] = nodelist

    if not components:
        raise GateError(f"netlist contains zero components: {path}")
    if not nets:
        raise GateError(f"netlist contains zero nets: {path}")

    return Netlist(
        components=components,
        nets=nets,
        net_nodes=net_nodes,
        pin_net=pin_net,
        ref_pins=ref_pins,
    )


def check_netlist_freshness(netlist_path: Path, src_dir: Path) -> None:
    """Fail closed if the compiled netlist predates any .ato source file.

    A stale netlist checking yesterday's design and reporting "0 violations"
    is indistinguishable from a correct check on today's design -- and is
    exactly the failure mode this class of gate has hit repeatedly on this
    project. `elec/build/` is gitignored; nothing else guarantees freshness.
    """
    if not netlist_path.is_file():
        raise GateError(
            f"netlist not found: {netlist_path} -- run `make netlist` first "
            "(elec/build/ is gitignored, so it must be built locally/in-CI, "
            "never assumed to already exist)"
        )
    netlist_mtime = netlist_path.stat().st_mtime
    if not src_dir.is_dir():
        raise GateError(f"elec source directory not found: {src_dir}")
    source_files = sorted(src_dir.rglob("*.ato"))
    if not source_files:
        raise GateError(f"no .ato source files found under {src_dir}")
    stale_against = [
        f for f in source_files if f.stat().st_mtime > netlist_mtime
    ]
    if stale_against:
        newest = max(stale_against, key=lambda f: f.stat().st_mtime)
        raise GateError(
            f"netlist is STALE: {newest} was modified after "
            f"{netlist_path} was built. Run `make netlist` to rebuild "
            f"before running this gate ({len(stale_against)} source "
            "file(s) newer than the compiled netlist)."
        )


# ---------------------------------------------------------------------------
# Domain manifest
# ---------------------------------------------------------------------------


@dataclass
class Isolator:
    instance_path: str
    component: str
    groups: dict[str, list[str]]  # group name -> [pin, ...]
    pin_labels: dict[str, str] = field(default_factory=dict)  # pin -> human label (display only)


@dataclass
class ProtectiveImpedanceChain:
    """A declared protective-impedance construction: an ORDERED series of
    two-terminal components (e.g. 3x430k resistors) between two named nets,
    where the safety property ("no single component failure removes the
    current-limiting function") depends on ALL declared members actually
    being present and wired in series -- not on any single one of them.

    Declaring only the first element as an isolator (as a single-component
    Isolator entry would) verifies nothing about the rest of the chain: a
    later edit that deletes or bypasses the second/third element would still
    pass a gate that only knows about the first. This declaration, together
    with check_chain_integrity, verifies the WHOLE chain: every member
    exists, is a genuine two-terminal part, is wired in series to its
    declared neighbor, and no interior node has an undeclared extra
    connection (a bypass/tap that would defeat the redundancy)."""

    name: str
    component: str
    chain: list[str]  # instance paths, in series order, boundary_a -> boundary_b
    boundary_a: str  # net name
    boundary_b: str  # net name
    min_length: int  # manifest-declared minimum series-element count


@dataclass
class Manifest:
    domains: dict[str, list[str]]  # domain name -> [net name, ...]
    isolators: list[Isolator]
    chains: list[ProtectiveImpedanceChain] = field(default_factory=list)


def load_manifest(path: Path) -> Manifest:
    if not path.is_file():
        raise GateError(f"domain manifest not found: {path}")
    raw_text = path.read_text(encoding="utf-8")
    if not raw_text.strip():
        raise GateError(f"domain manifest is empty: {path}")

    import yaml

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise GateError(f"domain manifest is not valid YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise GateError(f"domain manifest must be a mapping at the top level: {path}")

    domains_raw = data.get("domains")
    if not isinstance(domains_raw, dict) or not domains_raw:
        raise GateError(
            "domain manifest has no non-empty 'domains' mapping -- an "
            "empty or absent domain declaration must fail the gate, not "
            "pass it vacuously (METHODOLOGY.md Sec 5, anti-vacuous-truth)"
        )
    if len(domains_raw) < 2:
        raise GateError(
            "domain manifest declares fewer than 2 domains -- disjointness "
            "is not a meaningful question with only one domain"
        )

    domains: dict[str, list[str]] = {}
    net_owner: dict[str, str] = {}
    for domain_name, domain_body in domains_raw.items():
        if not isinstance(domain_body, dict):
            raise GateError(f"domain {domain_name!r} must be a mapping")
        nets = domain_body.get("nets")
        if not isinstance(nets, list) or not nets:
            raise GateError(
                f"domain {domain_name!r} has no non-empty 'nets' list -- "
                "an empty domain must fail the gate, not pass it vacuously"
            )
        cleaned = [str(n) for n in nets]
        for n in cleaned:
            if n in net_owner:
                raise GateError(
                    f"net {n!r} is declared under both domain "
                    f"{net_owner[n]!r} and {domain_name!r} -- a net cannot "
                    "belong to two domains at once; fix the manifest"
                )
            net_owner[n] = domain_name
        domains[str(domain_name)] = cleaned

    isolators_raw = data.get("isolators")
    if isolators_raw is None:
        isolators_raw = []
    if not isinstance(isolators_raw, list):
        raise GateError("'isolators' must be a list if present")

    isolators: list[Isolator] = []
    seen_paths: set[str] = set()
    for entry in isolators_raw:
        if not isinstance(entry, dict):
            raise GateError(f"isolator entry must be a mapping: {entry!r}")
        instance_path = entry.get("instance_path")
        component = entry.get("component", "")
        groups_raw = entry.get("groups")
        if not instance_path or not isinstance(instance_path, str):
            raise GateError(f"isolator entry missing 'instance_path': {entry!r}")
        if instance_path in seen_paths:
            raise GateError(f"duplicate isolator instance_path: {instance_path!r}")
        seen_paths.add(instance_path)
        if not isinstance(groups_raw, dict) or len(groups_raw) < 2:
            raise GateError(
                f"isolator {instance_path!r} must declare at least 2 pin "
                "groups (an isolator with 1 group isolates nothing)"
            )
        groups: dict[str, list[str]] = {}
        seen_pins: dict[str, str] = {}
        for group_name, pins in groups_raw.items():
            if not isinstance(pins, list) or not pins:
                raise GateError(
                    f"isolator {instance_path!r} group {group_name!r} must "
                    "be a non-empty list of pin numbers"
                )
            pins_str = [str(p) for p in pins]
            for p in pins_str:
                if p in seen_pins:
                    raise GateError(
                        f"isolator {instance_path!r} pin {p!r} is declared "
                        f"in both group {seen_pins[p]!r} and {group_name!r}"
                    )
                seen_pins[p] = str(group_name)
            groups[str(group_name)] = pins_str
        pin_labels_raw = entry.get("pin_labels", {})
        if not isinstance(pin_labels_raw, dict):
            raise GateError(f"isolator {instance_path!r} 'pin_labels' must be a mapping")
        pin_labels = {str(k): str(v) for k, v in pin_labels_raw.items()}
        isolators.append(
            Isolator(
                instance_path=instance_path,
                component=str(component),
                groups=groups,
                pin_labels=pin_labels,
            )
        )

    chains_raw = data.get("protective_impedance_chains")
    if chains_raw is None:
        chains_raw = []
    if not isinstance(chains_raw, list):
        raise GateError("'protective_impedance_chains' must be a list if present")

    chains: list[ProtectiveImpedanceChain] = []
    seen_chain_members: set[str] = set()
    seen_chain_names: set[str] = set()
    for entry in chains_raw:
        if not isinstance(entry, dict):
            raise GateError(f"protective_impedance_chain entry must be a mapping: {entry!r}")
        name = entry.get("name")
        component = entry.get("component", "")
        chain_raw = entry.get("chain")
        boundary_a = entry.get("boundary_a")
        boundary_b = entry.get("boundary_b")
        min_length = entry.get("min_length")
        if not name or not isinstance(name, str):
            raise GateError(f"protective_impedance_chain entry missing 'name': {entry!r}")
        if name in seen_chain_names:
            raise GateError(f"duplicate protective_impedance_chain name: {name!r}")
        seen_chain_names.add(name)
        if not isinstance(chain_raw, list) or len(chain_raw) < 2:
            raise GateError(
                f"protective_impedance_chain {name!r} must declare a 'chain' "
                "list of at least 2 component instance_paths -- a single "
                "component is not a redundant protective-impedance "
                "construction (use a plain 'isolators' entry for that)"
            )
        chain_paths = [str(c) for c in chain_raw]
        if len(set(chain_paths)) != len(chain_paths):
            raise GateError(
                f"protective_impedance_chain {name!r} lists the same "
                "instance_path more than once"
            )
        for p in chain_paths:
            if p in seen_chain_members:
                raise GateError(
                    f"instance_path {p!r} appears in more than one "
                    "protective_impedance_chain -- each physical component "
                    "backs at most one declared chain"
                )
            seen_chain_members.add(p)
        if not boundary_a or not isinstance(boundary_a, str):
            raise GateError(f"protective_impedance_chain {name!r} missing 'boundary_a'")
        if not boundary_b or not isinstance(boundary_b, str):
            raise GateError(f"protective_impedance_chain {name!r} missing 'boundary_b'")
        if not isinstance(min_length, int) or isinstance(min_length, bool) or min_length < 2:
            raise GateError(
                f"protective_impedance_chain {name!r} must declare an "
                "integer 'min_length' >= 2 -- the number of independent "
                "series elements required for 'no single failure removes "
                "the impedance' (IEC 60335-1 protective-impedance "
                "construction requirement)"
            )
        if min_length > len(chain_paths):
            raise GateError(
                f"protective_impedance_chain {name!r} declares "
                f"min_length={min_length} but only lists "
                f"{len(chain_paths)} chain member(s) -- the manifest's own "
                "declaration is internally inconsistent"
            )
        chains.append(
            ProtectiveImpedanceChain(
                name=str(name),
                component=str(component),
                chain=chain_paths,
                boundary_a=str(boundary_a),
                boundary_b=str(boundary_b),
                min_length=int(min_length),
            )
        )

    isolator_paths = {i.instance_path for i in isolators}
    overlap = isolator_paths & seen_chain_members
    if overlap:
        raise GateError(
            f"instance_path(s) {sorted(overlap)} are declared both as a "
            "standalone 'isolators' entry and as a 'protective_impedance_"
            "chains' member -- ambiguous double modeling of the same "
            "component's graph role"
        )

    return Manifest(domains=domains, isolators=isolators, chains=chains)


# ---------------------------------------------------------------------------
# Graph construction and reachability
# ---------------------------------------------------------------------------


@dataclass
class Graph:
    adjacency: dict[str, list[tuple[str, str]]] = field(default_factory=dict)

    def add_edge(self, a: str, b: str, label: str, weight: int = 1) -> None:
        if a == b:
            return
        self.adjacency.setdefault(a, []).append((b, label, weight))
        self.adjacency.setdefault(b, []).append((a, label, weight))

    def ensure_node(self, n: str) -> None:
        self.adjacency.setdefault(n, [])

    def without_labels(self, labels: set[str]) -> "Graph":
        """Return a copy of this graph with every edge carrying one of
        `labels` removed. Used to find multiple INDEPENDENT bridging paths
        between two domains rather than only the single shortest one --
        two real, separate crossings (e.g. a 2-resistor ADC-sense divider
        and an unrelated 4-resistor comparator-reference divider) must both
        be visible, not just whichever happens to have fewer hops."""
        pruned = Graph()
        for node, edges in self.adjacency.items():
            pruned.ensure_node(node)
            pruned.adjacency[node] = [
                (n, lbl, w) for n, lbl, w in edges if lbl not in labels
            ]
        return pruned


def resolve_isolator_refs(
    netlist: Netlist, isolators: list[Isolator]
) -> dict[str, Isolator]:
    """Map component ref -> Isolator declaration, validating that every
    declared isolator matches exactly one real component and that its
    groups exactly partition that component's actually-wired pins."""
    path_to_refs: dict[str, list[str]] = {}
    for ref, comp in netlist.components.items():
        path_to_refs.setdefault(comp.instance_path, []).append(ref)

    ref_isolator: dict[str, Isolator] = {}
    for iso in isolators:
        matches = path_to_refs.get(iso.instance_path, [])
        if not matches:
            raise GateError(
                f"isolator instance_path {iso.instance_path!r} matches no "
                "component in the netlist -- either the manifest is stale "
                "or this isolating component was removed from the design "
                "(in which case the domain boundary it protected may no "
                "longer be enforced by anything)"
            )
        if len(matches) > 1:
            raise GateError(
                f"isolator instance_path {iso.instance_path!r} matches "
                f"{len(matches)} components ({matches!r}) -- instance "
                "paths must be unique"
            )
        ref = matches[0]
        declared_pins = {p for pins in iso.groups.values() for p in pins}
        wired_pins = set(netlist.ref_pins.get(ref, []))
        missing_from_manifest = wired_pins - declared_pins
        missing_from_netlist = declared_pins - wired_pins
        if missing_from_manifest:
            raise GateError(
                f"isolator {iso.instance_path!r} (ref {ref}) has wired "
                f"pin(s) {sorted(missing_from_manifest)} not covered by any "
                "declared group -- an isolator with an undeclared pin is a "
                "gap in the model, not a clean bill of health"
            )
        if missing_from_netlist:
            raise GateError(
                f"isolator {iso.instance_path!r} (ref {ref}) declares "
                f"pin(s) {sorted(missing_from_netlist)} that are not wired "
                "in the netlist at all -- stale manifest"
            )
        ref_isolator[ref] = iso
    return ref_isolator


def build_name_to_code(netlist: Netlist) -> dict[str, str]:
    """Compiled net name -> net code, first-match-wins (mirrors the local
    helper previously inlined in check_domain_disjointness; factored out so
    check_chain_integrity can resolve boundary net names the same way)."""
    name_to_code: dict[str, str] = {}
    for code, name in netlist.nets.items():
        name_to_code.setdefault(name, code)
    return name_to_code


def resolve_chain_refs(
    netlist: Netlist, chains: list[ProtectiveImpedanceChain]
) -> dict[str, list[str]]:
    """Map chain name -> ordered list of component refs (same order as
    declared), validating that every chain member matches exactly one real
    component in the netlist and that it is a genuine two-terminal part.

    Fails closed exactly like resolve_isolator_refs: a chain member that has
    been deleted from the design (not just from the manifest) is the single
    most direct way this redundancy could quietly disappear, so a missing
    match is a GateError, not a silently-skipped chain link."""
    path_to_refs: dict[str, list[str]] = {}
    for ref, comp in netlist.components.items():
        path_to_refs.setdefault(comp.instance_path, []).append(ref)

    resolved: dict[str, list[str]] = {}
    for chain in chains:
        refs: list[str] = []
        for path in chain.chain:
            matches = path_to_refs.get(path, [])
            if not matches:
                raise GateError(
                    f"protective_impedance_chain {chain.name!r} member "
                    f"{path!r} matches no component in the netlist -- "
                    "either the manifest is stale or this component was "
                    "removed from the design, in which case the "
                    "protective-impedance construction it was declared to "
                    "be part of no longer exists as declared"
                )
            if len(matches) > 1:
                raise GateError(
                    f"protective_impedance_chain {chain.name!r} member "
                    f"{path!r} matches {len(matches)} components "
                    f"({matches!r}) -- instance paths must be unique"
                )
            ref = matches[0]
            wired = sorted(set(netlist.ref_pins.get(ref, [])))
            if len(wired) != 2:
                raise GateError(
                    f"protective_impedance_chain {chain.name!r} member "
                    f"{path!r} (ref {ref}) has {len(wired)} wired pin(s) "
                    f"{wired}, not exactly 2 -- chain members must be plain "
                    "two-terminal components; a part with more pins cannot "
                    "be modeled as a single series link"
                )
            refs.append(ref)
        resolved[chain.name] = refs
    return resolved


def synthesize_chain_head_isolators(
    netlist: Netlist,
    chains: list[ProtectiveImpedanceChain],
    resolved: dict[str, list[str]],
    name_to_code: dict[str, str],
) -> dict[str, Isolator]:
    """For each declared chain, synthesize an Isolator for its FIRST member
    only, so the existing graph machinery (build_graph / check_domain_
    disjointness / check_isolator_integrity) treats that one component as
    blocking -- exactly as it would a single-component 'isolators' entry --
    which is sufficient to disconnect boundary_a from everything downstream
    in the reachability graph. The remaining chain members are deliberately
    left as ORDINARY, undeclared (fully-conductive) components in the graph:
    they genuinely do conduct, and declaring them as graph-isolators too
    caused false isolator-barrier violations in practice (a chain's last
    resistor's own two nets are legitimately, separately reconnected
    elsewhere in the SELV domain -- e.g. through the comparator IC's own
    pins, or a decoupling capacitor -- which is not a barrier breach).
    check_chain_integrity (a separate, direct netlist inspection, not a
    graph-reachability check) is what verifies the REST of the chain is
    actually present and wired in series, without that false-positive
    failure mode."""
    boundary_a_code = {c.name: name_to_code.get(c.boundary_a) for c in chains}
    head_isolators: dict[str, Isolator] = {}
    for chain in chains:
        a_code = boundary_a_code[chain.name]
        if a_code is None:
            raise GateError(
                f"protective_impedance_chain {chain.name!r} boundary_a "
                f"{chain.boundary_a!r} does not exist in the compiled "
                "netlist -- typo, or the design changed and the manifest "
                "is stale"
            )
        head_ref = resolved[chain.name][0]
        pins = sorted(set(netlist.ref_pins.get(head_ref, [])))
        pin_nets = {p: netlist.pin_net[(head_ref, p)] for p in pins}
        entry_pins = [p for p, net in pin_nets.items() if net == a_code]
        if not entry_pins:
            raise GateError(
                f"protective_impedance_chain {chain.name!r}'s first member "
                f"{chain.chain[0]!r} (ref {head_ref}) does not have either "
                f"of its pins on the declared boundary_a net "
                f"{chain.boundary_a!r} -- the chain is not wired as "
                "declared, so this manifest entry cannot be trusted to "
                "model the design"
            )
        entry_pin = entry_pins[0]
        other_pins = [p for p in pins if p != entry_pin]
        if len(other_pins) != 1:
            raise GateError(
                f"protective_impedance_chain {chain.name!r}'s first member "
                f"{chain.chain[0]!r} (ref {head_ref}) has both pins on "
                f"boundary_a {chain.boundary_a!r} -- effectively shorted, "
                "which cannot be the intended protective-impedance element"
            )
        head_isolators[head_ref] = Isolator(
            instance_path=chain.chain[0],
            component=chain.component,
            groups={
                "boundary_a_side": [entry_pin],
                "chain_interior": [other_pins[0]],
            },
            pin_labels={
                entry_pin: f"boundary_a ({chain.boundary_a})",
                other_pins[0]: "-> rest of declared protective-impedance chain",
            },
        )
    return head_isolators


def _dedupe_nets_in_pin_order(netlist: Netlist, ref: str, pins: list[str]) -> list[str]:
    """Unique nets touched by `pins`, ordered by pin number (numeric where
    possible). Used to chain a multi-pin component's nets pin1-pin2-pin3-...
    rather than hub everything through whichever pin happened to be listed
    first in the netlist file. A star topology from an arbitrary hub pin
    creates a false "1-hop shortcut" between two pins of a many-pin IC that
    have nothing to do with each other electrically (e.g. a comparator's
    GND pin and its INP pin) -- which can bury a real, more informative
    passive-component path (e.g. a divider's own bottom resistor) behind an
    arbitrary equal-length route through an unrelated IC pin. A pin-order
    chain is still the same fail-closed "this component conducts across all
    its pins" assumption (same reachability, same total edges), it just
    does not manufacture spurious 1-hop adjacency between unrelated pins."""

    def _pin_key(pin: str) -> tuple[int, object]:
        try:
            return (0, int(pin))
        except ValueError:
            return (1, pin)

    ordered_pins = sorted(pins, key=_pin_key)
    nets_here: list[str] = []
    seen: set[str] = set()
    for p in ordered_pins:
        net = netlist.pin_net[(ref, p)]
        if net not in seen:
            nets_here.append(net)
            seen.add(net)
    return nets_here


def build_graph(netlist: Netlist, ref_isolator: dict[str, Isolator]) -> Graph:
    graph = Graph()
    for code in netlist.nets:
        graph.ensure_node(code)

    for ref, pins in netlist.ref_pins.items():
        comp = netlist.components.get(ref)
        instance_path = comp.instance_path if comp else ref
        iso = ref_isolator.get(ref)
        if iso is not None:
            # Conductive only WITHIN each declared group -- never across.
            for group_name, group_pins in iso.groups.items():
                wired_group_pins = [p for p in group_pins if p in pins]
                nets_in_group = _dedupe_nets_in_pin_order(netlist, ref, wired_group_pins)
                label = f"{instance_path} ({iso.component}) [{group_name} group]"
                # Weight 0 for a genuine two-terminal element (a real single
                # physical part with exactly two nodes -- conducting between
                # them is a fact about the part, not a modeling assumption);
                # weight 1 for anything wider. Cheapest-path search then
                # prefers a chain of plain two-terminal parts (e.g. a
                # resistor divider) over an equal-hop-count route that
                # happens to pass through an arbitrary pair of an unrelated
                # multi-pin IC's pins, without discarding the IC route
                # entirely -- it is still found, just not preferred on ties.
                weight = 0 if len(nets_in_group) <= 2 else 1
                for i in range(1, len(nets_in_group)):
                    graph.add_edge(nets_in_group[i - 1], nets_in_group[i], label, weight)
        else:
            # Default, conservative assumption: an undeclared component
            # conducts across all of its own pins. This is the fail-closed
            # direction -- treating an unknown part as isolating is how a
            # real short gets missed; treating it as conductive can only
            # produce a false positive that a human then has to adjudicate,
            # never a silently missed hazard.
            nets_here = _dedupe_nets_in_pin_order(netlist, ref, pins)
            label = ref if not instance_path else f"{instance_path} ({ref})"
            weight = 0 if len(nets_here) <= 2 else 1
            for i in range(1, len(nets_here)):
                graph.add_edge(nets_here[i - 1], nets_here[i], label, weight)

    return graph


def connected_components(graph: Graph) -> dict[str, int]:
    """Return {net_code: component_id}."""
    component_of: dict[str, int] = {}
    next_id = 0
    for start in graph.adjacency:
        if start in component_of:
            continue
        component_of[start] = next_id
        queue = deque([start])
        while queue:
            node = queue.popleft()
            for neighbor, _label, _weight in graph.adjacency.get(node, []):
                if neighbor not in component_of:
                    component_of[neighbor] = next_id
                    queue.append(neighbor)
        next_id += 1
    return component_of


def shortest_path(graph: Graph, start: str, goal: str) -> list[tuple[str, str]]:
    """BFS shortest path from start to goal."""
    return multi_source_shortest_path(graph, {start}, {goal})


def multi_source_shortest_path(
    graph: Graph, sources: set[str], targets: set[str]
) -> list[tuple[str, str]]:
    """Multi-source 0-1 BFS: the CHEAPEST path from ANY of `sources` to ANY
    of `targets`, where a genuine two-terminal component (weight 0) is
    preferred over an equal-hop-count route through an arbitrary pair of an
    unrelated multi-pin IC's pins (weight 1) -- see build_graph's weight
    assignment. This is what lets the report show a plain resistor-divider
    bridge (e.g. dc_bus_plus -> 430k -> 430k -> 430k -> 10k -> gnd) rather
    than an equally-short-by-hop-count but less informative route through
    some unrelated IC's assumed full-pin conductivity, without ever hiding
    the IC route -- it is simply not preferred when a two-terminal-only
    route of equal or lower cost exists. Falls back to plain hop-count
    ordering among equal-weight routes (0-1 BFS is still a real shortest-
    path algorithm, not a heuristic reordering).

    Returns a list of (net_code, edge_label_used_to_arrive), starting with
    (source, "")."""
    # Sort every set-derived iteration order below. Python randomizes str
    # hashing per-process (PYTHONHASHSEED), so iterating a set directly
    # would make which of several EQUALLY VALID shortest paths gets
    # reported vary between runs on byte-identical input -- the same
    # oracle-reproducibility failure METHODOLOGY.md Sec 5 requires
    # checking for in third-party tools applies to this script's own
    # internals too.
    common = sources & targets
    if common:
        n = min(common)
        return [(n, "")]

    dist: dict[str, int] = {s: 0 for s in sorted(sources)}
    parent: dict[str, tuple[str, str]] = {}
    finalized: set[str] = set()
    dq: deque[str] = deque(sorted(sources))

    while dq:
        node = dq.popleft()
        if node in finalized:
            continue
        finalized.add(node)
        if node in targets and node not in sources:
            path: list[tuple[str, str]] = []
            cur: str | None = node
            while cur is not None:
                if cur in parent:
                    prev, label = parent[cur]
                    path.append((cur, label))
                    cur = prev
                else:
                    path.append((cur, ""))
                    cur = None
            path.reverse()
            return path
        for neighbor, label, weight in graph.adjacency.get(node, []):
            if neighbor in finalized:
                continue
            new_dist = dist[node] + weight
            if neighbor not in dist or new_dist < dist[neighbor]:
                dist[neighbor] = new_dist
                parent[neighbor] = (node, label)
                if weight == 0:
                    dq.appendleft(neighbor)
                else:
                    dq.append(neighbor)
    raise GateError(
        "internal error: no BFS path found between declared-same-component "
        "source/target sets"
    )


def find_independent_paths(
    graph: Graph, sources: set[str], targets: set[str], max_paths: int = 5
) -> list[list[tuple[str, str]]]:
    """Find up to `max_paths` independent bridging paths between `sources`
    and `targets`, not just the single shortest one.

    After each path is found, every component (edge label) it used is
    removed from a working copy of the graph before searching again. This
    guarantees a second, unrelated bridge (a different divider, a different
    undeclared component) is not hidden just because it happens to be a few
    hops longer than the first one found -- both are real evidence and both
    must be reported (METHODOLOGY.md: extra findings are the point, not
    noise). Stops when no more paths exist or `max_paths` is reached.
    """
    paths: list[list[tuple[str, str]]] = []
    working = graph
    for _ in range(max_paths):
        try:
            path = multi_source_shortest_path(working, sources, targets)
        except GateError:
            break
        paths.append(path)
        used_labels = {label for _net, label in path if label}
        if not used_labels:
            break
        working = working.without_labels(used_labels)
    return paths


def format_path(netlist: Netlist, path: list[tuple[str, str]]) -> str:
    parts = []
    for i, (code, label) in enumerate(path):
        name = netlist.nets.get(code, code)
        if i == 0:
            parts.append(f"{name!r}")
        else:
            parts.append(f" --[{label}]--> {name!r}")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


@dataclass
class DomainViolation:
    domain_a: str
    domain_b: str
    path_descs: list[str]  # one or more INDEPENDENT bridging paths, shortest first
    component_id: int


@dataclass
class IsolatorViolation:
    instance_path: str
    component: str
    ref: str
    group_a: str
    group_b: str
    pin_a: str
    pin_b: str
    label_a: str
    label_b: str
    net_a: str
    net_b: str
    path_desc: str


def check_domain_disjointness(
    netlist: Netlist,
    manifest: Manifest,
    graph: Graph,
    component_of: dict[str, int],
) -> list[DomainViolation]:
    # Map compiled net name -> code, validating every declared net exists.
    name_to_code = build_name_to_code(netlist)

    domain_codes: dict[str, list[str]] = {}
    missing: list[str] = []
    for domain, net_names in manifest.domains.items():
        codes = []
        for n in net_names:
            code = name_to_code.get(n)
            if code is None:
                missing.append(f"{domain}:{n}")
            else:
                codes.append(code)
        domain_codes[domain] = codes
    if missing:
        raise GateError(
            "domain manifest declares net(s) that do not exist in the "
            f"compiled netlist: {missing} -- typo, or the design changed "
            "and the manifest is stale"
        )

    # Group declared nets, per domain, by connected-component id.
    domain_names = sorted(domain_codes)
    violations: list[DomainViolation] = []
    reported_components: set[tuple[int, frozenset]] = set()
    for i, domain_a in enumerate(domain_names):
        for domain_b in domain_names[i + 1 :]:
            comp_to_nets_a: dict[int, list[str]] = {}
            for code in domain_codes[domain_a]:
                comp_to_nets_a.setdefault(component_of[code], []).append(code)
            comp_to_nets_b: dict[int, list[str]] = {}
            for code in domain_codes[domain_b]:
                comp_to_nets_b.setdefault(component_of[code], []).append(code)
            shared = set(comp_to_nets_a) & set(comp_to_nets_b)
            for comp_id in sorted(shared):
                key = (comp_id, frozenset({domain_a, domain_b}))
                if key in reported_components:
                    continue
                reported_components.add(key)
                # Multi-source BFS over ALL declared nets of each domain in
                # this shared component -- picks the most direct evidence
                # available (e.g. the isolator's own two pins) rather than
                # whichever net happened to be listed first in the manifest.
                # find_independent_paths additionally re-searches with each
                # found bridge's components removed, so a SECOND, unrelated
                # crossing (e.g. a different resistor divider) is reported
                # too, not hidden just because it has more hops than the
                # first one found.
                paths = find_independent_paths(
                    graph, set(comp_to_nets_a[comp_id]), set(comp_to_nets_b[comp_id])
                )
                violations.append(
                    DomainViolation(
                        domain_a=domain_a,
                        domain_b=domain_b,
                        path_descs=[format_path(netlist, p) for p in paths],
                        component_id=comp_id,
                    )
                )
    return violations


def check_isolator_integrity(
    netlist: Netlist,
    ref_isolator: dict[str, Isolator],
    graph: Graph,
    component_of: dict[str, int],
) -> list[IsolatorViolation]:
    violations: list[IsolatorViolation] = []
    for ref, iso in ref_isolator.items():
        group_names = sorted(iso.groups)
        group_nets: dict[str, list[str]] = {}
        # One pin-lookup table PER GROUP -- not shared across groups. If the
        # same net code appears in two different groups (exactly the short
        # this gate exists to catch), a single shared dict would let the
        # first group's pin silently shadow the second group's, misreporting
        # which pin is on which side of the (defeated) barrier.
        net_to_pin_by_group: dict[str, dict[str, str]] = {}
        for gname, pins in iso.groups.items():
            nets_here = []
            pin_lookup: dict[str, str] = {}
            for p in pins:
                if (ref, p) not in netlist.pin_net:
                    continue
                code = netlist.pin_net[(ref, p)]
                nets_here.append(code)
                pin_lookup.setdefault(code, p)
            group_nets[gname] = nets_here
            net_to_pin_by_group[gname] = pin_lookup
        for i, ga in enumerate(group_names):
            for gb in group_names[i + 1 :]:
                comps_a = {component_of[c] for c in group_nets[ga]}
                comps_b = {component_of[c] for c in group_nets[gb]}
                shared = comps_a & comps_b
                if not shared:
                    continue
                comp_id = min(shared)  # deterministic pick; see note in multi_source_shortest_path
                nets_a_here = {c for c in group_nets[ga] if component_of[c] == comp_id}
                nets_b_here = {c for c in group_nets[gb] if component_of[c] == comp_id}
                path = multi_source_shortest_path(graph, nets_a_here, nets_b_here)
                net_a, net_b = path[0][0], path[-1][0]
                violations.append(
                    IsolatorViolation(
                        instance_path=iso.instance_path,
                        component=iso.component,
                        ref=ref,
                        group_a=ga,
                        group_b=gb,
                        pin_a=net_to_pin_by_group[ga][net_a],
                        pin_b=net_to_pin_by_group[gb][net_b],
                        label_a=iso.pin_labels.get(net_to_pin_by_group[ga][net_a], ""),
                        label_b=iso.pin_labels.get(net_to_pin_by_group[gb][net_b], ""),
                        net_a=netlist.nets[net_a],
                        net_b=netlist.nets[net_b],
                        path_desc=format_path(netlist, path),
                    )
                )
    return violations


@dataclass
class ChainViolation:
    name: str
    component: str
    reason: str
    detail: str


def check_chain_integrity(
    netlist: Netlist,
    chains: list[ProtectiveImpedanceChain],
    resolved: dict[str, list[str]],
    name_to_code: dict[str, str],
) -> list[ChainViolation]:
    """Verify each declared protective-impedance chain is ACTUALLY wired as
    an unbroken series of its declared members, end to end -- not merely
    that its first member exists (that much is already guaranteed by
    synthesize_chain_head_isolators / resolve_chain_refs raising GateError
    for a missing component).

    This is a direct netlist inspection, independent of the reachability
    graph: it walks the declared chain link by link, and for every INTERIOR
    node (between two consecutive chain members) demands that node connect
    ONLY those two members' declared pins -- nothing else. A component that
    is deleted is already caught earlier (GateError); a component that is
    still present but bypassed (an added jumper/wire tying two interior
    nodes together, or shorting a member's own two pins) collapses net
    codes in a way this walk catches directly, without needing to know any
    resistance VALUE at all (the compiled netlist does not reliably carry
    resistor values -- see the evidence doc -- so this checks topology,
    which it does carry, and which is exactly what 'no single failure
    removes the impedance' depends on structurally)."""
    violations: list[ChainViolation] = []
    for chain in chains:
        refs = resolved[chain.name]
        a_code = name_to_code.get(chain.boundary_a)
        b_code = name_to_code.get(chain.boundary_b)
        if a_code is None:
            raise GateError(
                f"protective_impedance_chain {chain.name!r} boundary_a "
                f"{chain.boundary_a!r} does not exist in the compiled netlist"
            )
        if b_code is None:
            raise GateError(
                f"protective_impedance_chain {chain.name!r} boundary_b "
                f"{chain.boundary_b!r} does not exist in the compiled netlist"
            )

        current = a_code
        for i, ref in enumerate(refs):
            path = chain.chain[i]
            pins = sorted(set(netlist.ref_pins.get(ref, [])))
            if len(pins) != 2:
                violations.append(
                    ChainViolation(
                        chain.name, chain.component, "malformed-member",
                        f"{ref} ({path}) does not have exactly 2 wired pins "
                        f"({pins}) -- cannot be a series link",
                    )
                )
                break
            p_a, p_b = pins
            net_a = netlist.pin_net[(ref, p_a)]
            net_b = netlist.pin_net[(ref, p_b)]
            if net_a == net_b:
                violations.append(
                    ChainViolation(
                        chain.name, chain.component, "member-shorted",
                        f"{ref} ({path}) has both pins ({p_a}, {p_b}) on the "
                        f"same net {netlist.nets[net_a]!r} -- effectively "
                        "shorted or removed from the circuit, defeating the "
                        "protective-impedance construction",
                    )
                )
                break
            if current == net_a:
                exit_pin, exit_net = p_b, net_b
            elif current == net_b:
                exit_pin, exit_net = p_a, net_a
            else:
                violations.append(
                    ChainViolation(
                        chain.name, chain.component, "chain-broken",
                        f"{ref} ({path}) does not connect to the expected "
                        f"upstream node {netlist.nets.get(current, current)!r} "
                        f"(its pins are on {netlist.nets[net_a]!r} and "
                        f"{netlist.nets[net_b]!r}) -- the declared series "
                        "chain is not actually wired as declared",
                    )
                )
                break

            is_last = i == len(refs) - 1
            if is_last:
                if exit_net != b_code:
                    violations.append(
                        ChainViolation(
                            chain.name, chain.component, "chain-wrong-terminus",
                            f"{ref} ({path}) terminates on "
                            f"{netlist.nets[exit_net]!r}, not the declared "
                            f"boundary_b {chain.boundary_b!r}",
                        )
                    )
                    break
            else:
                next_ref = refs[i + 1]
                nodes_here = netlist.net_nodes.get(exit_net, [])
                other_nodes = [
                    (r, p) for (r, p) in nodes_here if not (r == ref and p == exit_pin)
                ]
                unexpected = [(r, p) for (r, p) in other_nodes if r != next_ref]
                if unexpected:
                    violations.append(
                        ChainViolation(
                            chain.name, chain.component, "chain-tapped",
                            f"interior node {netlist.nets[exit_net]!r} "
                            f"between {ref} ({path}) and the declared next "
                            f"member {next_ref} ({chain.chain[i + 1]}) has "
                            f"additional connection(s) {unexpected} -- a "
                            "possible bypass/tap defeating the declared "
                            "protective-impedance chain",
                        )
                    )
                    break
                touching_next = [(r, p) for (r, p) in other_nodes if r == next_ref]
                if len(touching_next) != 1:
                    violations.append(
                        ChainViolation(
                            chain.name, chain.component, "chain-broken",
                            f"interior node {netlist.nets[exit_net]!r} does "
                            f"not connect {ref} ({path}) to exactly one pin "
                            f"of the declared next member {next_ref} "
                            f"({chain.chain[i + 1]}) (found {touching_next})",
                        )
                    )
                    break
            current = exit_net
    return violations


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(netlist_path: Path, manifest_path: Path, src_dir: Path, skip_freshness: bool = False) -> int:
    try:
        if not skip_freshness:
            check_netlist_freshness(netlist_path, src_dir)
        netlist = parse_netlist(netlist_path)
        manifest = load_manifest(manifest_path)
        ref_isolator = resolve_isolator_refs(netlist, manifest.isolators)
        name_to_code = build_name_to_code(netlist)
        chain_refs = resolve_chain_refs(netlist, manifest.chains)
        head_isolators = synthesize_chain_head_isolators(
            netlist, manifest.chains, chain_refs, name_to_code
        )
        ref_isolator.update(head_isolators)
        graph = build_graph(netlist, ref_isolator)
        component_of = connected_components(graph)

        # Anti-vacuous-truth: confirm the check actually ran over non-empty,
        # real data before any verdict is trusted. Uses explicit checks
        # (not `assert`) so this cannot be silently compiled away under
        # `python -O` -- a safety gate's guardrails must not be optional.
        n_domain_nets = sum(len(v) for v in manifest.domains.values())
        if n_domain_nets == 0:
            raise GateError("no domain nets to check (should have been caught earlier)")
        if len(netlist.nets) == 0:
            raise GateError("no nets in netlist (should have been caught earlier)")

        domain_violations = check_domain_disjointness(netlist, manifest, graph, component_of)
        isolator_violations = check_isolator_integrity(
            netlist, ref_isolator, graph, component_of
        )
        chain_violations = check_chain_integrity(
            netlist, manifest.chains, chain_refs, name_to_code
        )
    except GateError as exc:
        print("=== DOMAIN-PARTITION GATE ERROR ===", file=sys.stderr)
        print(f"Reason: {exc}", file=sys.stderr)
        print(
            "GATE RESULT: ERROR -- not PASSED, not a violation. The gate "
            "could not run a trustworthy check.",
            file=sys.stderr,
        )
        gh = get_github_summary_path()
        if gh:
            with open(gh, "a") as f:
                f.write("### Netlist Domain-Partition Gate -- GATE ERROR\n")
                f.write(f"{exc}\n")
        return EXIT_GATE_ERROR

    print(f"Netlist: {netlist_path}")
    print(f"Manifest: {manifest_path}")
    print(
        f"Checked {sum(len(v) for v in manifest.domains.values())} declared "
        f"nets across {len(manifest.domains)} domains "
        f"({', '.join(sorted(manifest.domains))}), "
        f"{len(ref_isolator)} declared isolators, "
        f"{len(manifest.chains)} declared protective-impedance chain(s) "
        f"({sum(len(c.chain) for c in manifest.chains)} chain member(s) "
        "total), over "
        f"{len(netlist.nets)} compiled nets / {len(netlist.components)} "
        "components."
    )

    # Informational only (does not affect the exit code): a net record with
    # zero nodes is a dangling/unused signal declaration in the source --
    # not a domain violation, but worth a human glance, since an empty net
    # is also exactly the shape of bug that could one day silently hide a
    # forgotten connection.
    empty_nets = sorted(
        name for code, name in netlist.nets.items() if not netlist.net_nodes.get(code)
    )
    if empty_nets:
        print(
            f"\nNOTE: {len(empty_nets)} net record(s) with zero connected "
            f"pins (dangling signal declarations, not a violation): "
            f"{empty_nets}"
        )

    gh = get_github_summary_path()
    gh_lines: list[str] = []

    if not domain_violations and not isolator_violations and not chain_violations:
        print(
            "\nPASSED -- 0 domain crossings, 0 isolator-barrier breaches, "
            "0 protective-impedance chain defects"
        )
        if gh:
            with open(gh, "a") as f:
                f.write("### Netlist Domain-Partition Gate -- PASSED\n")
                f.write(
                    f"0 violations across {len(manifest.domains)} domains, "
                    f"{len(ref_isolator)} isolators, "
                    f"{len(manifest.chains)} protective-impedance chains.\n"
                )
        return EXIT_OK

    print(
        f"\n=== DOMAIN VIOLATIONS: {len(domain_violations)} ==="
        if domain_violations
        else "\n=== DOMAIN VIOLATIONS: 0 ==="
    )
    for v in domain_violations:
        print(
            f"\n  Domain {v.domain_a!r} and domain {v.domain_b!r} are NOT "
            f"disjoint ({len(v.path_descs)} independent bridge(s) found):"
        )
        for j, desc in enumerate(v.path_descs, start=1):
            print(f"    [{j}] {desc}")
            gh_lines.append(f"- `{v.domain_a}` <-> `{v.domain_b}` [{j}]: {desc}")

    print(
        f"\n=== ISOLATOR BARRIER VIOLATIONS: {len(isolator_violations)} ==="
        if isolator_violations
        else "\n=== ISOLATOR BARRIER VIOLATIONS: 0 ==="
    )
    for v in isolator_violations:
        print(
            f"\n  Isolator {v.instance_path!r} ({v.component}): "
            f"group {v.group_a!r} and group {v.group_b!r} are reachable "
            "from each other -- this isolator's barrier is bridged:"
        )
        label_a = f" [{v.label_a}]" if v.label_a else ""
        label_b = f" [{v.label_b}]" if v.label_b else ""
        print(
            f"    {v.ref} pin {v.pin_a}{label_a} (group {v.group_a!r}, net {v.net_a!r}) "
            f"<-> {v.ref} pin {v.pin_b}{label_b} (group {v.group_b!r}, net {v.net_b!r})"
        )
        print(f"    path: {v.path_desc}")
        gh_lines.append(
            f"- `{v.instance_path}` pin {v.pin_a} [{v.group_a}] <-> "
            f"pin {v.pin_b} [{v.group_b}]: {v.path_desc}"
        )

    print(
        f"\n=== PROTECTIVE-IMPEDANCE CHAIN VIOLATIONS: {len(chain_violations)} ==="
        if chain_violations
        else "\n=== PROTECTIVE-IMPEDANCE CHAIN VIOLATIONS: 0 ==="
    )
    for v in chain_violations:
        print(f"\n  Chain {v.name!r} ({v.component}): [{v.reason}]")
        print(f"    {v.detail}")
        gh_lines.append(f"- `{v.name}` [{v.reason}]: {v.detail}")

    if gh:
        with open(gh, "a") as f:
            f.write("### Netlist Domain-Partition Gate -- FAILED\n")
            f.write(
                f"{len(domain_violations)} domain violation(s), "
                f"{len(isolator_violations)} isolator violation(s), "
                f"{len(chain_violations)} protective-impedance chain "
                "violation(s)\n\n"
            )
            for line in gh_lines:
                f.write(line + "\n")

    print(
        f"\nFAILED -- {len(domain_violations)} domain violation(s), "
        f"{len(isolator_violations)} isolator barrier violation(s), "
        f"{len(chain_violations)} protective-impedance chain violation(s)"
    )
    return EXIT_VIOLATION


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--netlist", type=Path, default=DEFAULT_NETLIST)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--src-dir", type=Path, default=DEFAULT_SRC_DIR)
    parser.add_argument(
        "--skip-freshness-check",
        action="store_true",
        help="Skip the netlist-vs-source mtime staleness check (test fixtures only).",
    )
    args = parser.parse_args()
    sys.exit(run(args.netlist, args.manifest, args.src_dir, args.skip_freshness_check))


if __name__ == "__main__":
    main()
