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
import re as _re
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.freshness import check_freshness
from _lib.github_summary import get_github_summary_path
from _lib.repo import find_repo_root

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
    """Fail closed if the compiled netlist was not built from current sources.

    A stale netlist checking yesterday's design and reporting "0 violations"
    is indistinguishable from a correct check on today's design -- and is
    exactly the failure mode this class of gate has hit repeatedly on this
    project. `elec/build/` is gitignored; nothing else guarantees freshness.

    Freshness is decided by CONTENT when `make netlist` left a build stamp
    beside the netlist, and by the legacy mtime comparison when it did not.
    See scripts/_lib/freshness.py for why: mtime cannot distinguish "rebuilt
    from unchanged sources" from "restored from cache", because `git checkout`
    stamps every source with the checkout time. That made a cached netlist
    permanently, wrongly STALE -- measured 2026-07-28, runs 30383701486
    (rebuilt, passed) vs 30384514627 (cached, errored) on identical sources.

    Content is also strictly stronger than mtime, not merely cache-friendly:
    a source edited and then back-dated older than the netlist passes the
    mtime check and fails the content check.
    """
    if not netlist_path.is_file():
        raise GateError(
            f"netlist not found: {netlist_path} -- run `make netlist` first "
            "(elec/build/ is gitignored, so it must be built locally/in-CI, "
            "never assumed to already exist)"
        )
    if not src_dir.is_dir():
        raise GateError(f"elec source directory not found: {src_dir}")
    source_files = sorted(src_dir.rglob("*.ato"))
    if not source_files:
        raise GateError(f"no .ato source files found under {src_dir}")

    result = check_freshness(netlist_path, source_files, src_dir)
    if not result.fresh:
        raise GateError(
            f"netlist is STALE: {result.detail}. Run `make netlist` to rebuild "
            f"before running this gate (freshness checked by {result.method})."
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


@dataclass(frozen=True)
class BoardInterfaceSignal:
    """One declared conductor in the future board-to-board interface.

    The manifest is deliberately more specific than a list of net names:
    ``nets`` protects the compiled-net boundary, while these records preserve
    the electrical contract that a board generator must consume.  ``None`` is
    permitted only for fields whose record is explicitly marked unresolved;
    silently defaulting an owner, direction, or fault action would turn an
    incomplete split into a plausible-looking board.
    """

    net: str
    role: str
    owner: str | None
    direction: str | None
    domain: str
    return_net: str | None
    fault_behavior: str | None
    status: str


@dataclass(frozen=True)
class BoardInterface:
    """The contract for the future power/control board connector.

    This is intentionally a net-level contract, not a claim that the current
    single-board PCB has already been split.  The physical split is a separate
    CAD deliverable; this contract makes it impossible to silently add an HV
    net to the board-to-board connector while that work is in progress.
    """

    name: str
    power_board: str
    control_board: str
    connector: str
    nets: tuple[str, ...]
    allowed_domains: tuple[str, ...]
    signals: tuple[BoardInterfaceSignal, ...] = ()
    safety_target: dict[str, Any] = field(default_factory=dict)
    connector_spec: dict[str, Any] = field(default_factory=dict)
    mechanical_spec: dict[str, Any] = field(default_factory=dict)
    generation_spec: dict[str, Any] = field(default_factory=dict)
    fault_aggregation: dict[str, Any] = field(default_factory=dict)
    deferred_signals: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class IsolatorBoardSides:
    """Map an isolator's manifest pin groups to the future board domains.

    The mapping is intentionally expressed in terms of the isolator's named
    groups, not pad numbers or refdes.  It therefore remains stable when the
    legacy one-board artifact is renumbered, while still making the intended
    power/control side of every barrier explicit.
    """

    instance_path: str
    power_board_group: str
    control_board_group: str


@dataclass(frozen=True)
class BoardPartition:
    """Planned ownership for the split-board migration.

    This is a source contract only.  ``status`` must remain ``planned``
    until a later CAD change creates two physical board artifacts.  Keeping
    the partition here, alongside the exact domain manifest, prevents a
    future split from silently moving a domain or an isolator side without
    changing the reviewed source contract.
    """

    status: str
    power_board: str
    control_board: str
    board_domains: dict[str, str]
    modules: dict[str, tuple[str, ...]]
    components: dict[str, tuple[str, ...]]
    cross_domain_components: tuple[dict[str, Any], ...]
    isolator_sides: tuple[IsolatorBoardSides, ...]
    cross_domain_modules: tuple[str, ...]


@dataclass
class Manifest:
    domains: dict[str, list[str]]  # domain name -> [net name, ...]
    isolators: list[Isolator]
    chains: list[ProtectiveImpedanceChain] = field(default_factory=list)
    board_interface: BoardInterface | None = None
    board_partition: BoardPartition | None = None


# This is deliberately an authority in the validator, not a convenience
# copied from the current YAML.  Adding a new readiness dependency must be a
# reviewed change to both the contract and this gate; otherwise a typo or a
# silently omitted field can make a generator appear ready.
MANDATORY_GENERATION_REQUIRED_FIELDS = frozenset(
    {
        "connector_spec.part_number",
        "connector_spec.pinout",
        "connector_spec.retention",
        "connector_spec.single_fault_review",
        "mechanical_spec.enclosure_compartment",
        "mechanical_spec.board_partition",
        "mechanical_spec.cable_routing",
        "mechanical_spec.mounting",
    }
)


def _source_component_inventory(src_dir: Path) -> tuple[set[str], set[str]]:
    """Return ``(top_level_modules, physical_component_paths)`` from Atopile.

    Atopile's compiled netlist carries the same dotted instance paths, but a
    split-board contract must be source-backed before a netlist is available.
    This small parser intentionally understands only declarations (module
    bodies and ``new`` assignments); it never infers ownership from names or
    values.  Unknown ``new`` types are electrical interfaces/constraints and
    are not physical components.
    """
    if not src_dir.is_dir():
        raise GateError(f"Atopile source directory not found: {src_dir}")
    module_defs: dict[str, list[tuple[str, str]]] = {}
    component_types: set[str] = set()
    for source in sorted(src_dir.glob("*.ato")):
        text = source.read_text(encoding="utf-8")
        component_types.update(_re.findall(r"^component\s+(\w+)\s*:", text, _re.M))
        modules = list(_re.finditer(r"^module\s+(\w+)\s*:", text, _re.M))
        for index, match in enumerate(modules):
            end = modules[index + 1].start() if index + 1 < len(modules) else len(text)
            body = text[match.end() : end]
            module_defs[match.group(1)] = [
                (name, type_name)
                for name, type_name in _re.findall(
                    r"^ {4}([A-Za-z_]\w*)\s*=\s*new\s+([A-Za-z_]\w*)",
                    body,
                    _re.M,
                )
            ]

    if "Top" not in module_defs:
        raise GateError(f"Atopile source has no Top module under {src_dir}")
    def has_physical_component(module_name: str, active: tuple[str, ...] = ()) -> bool:
        if module_name in active:
            raise GateError(
                "cycle in Atopile module declarations: "
                + " -> ".join((*active, module_name))
            )
        return any(
            type_name in component_types
            or (
                type_name in module_defs
                and has_physical_component(type_name, (*active, module_name))
            )
            for _, type_name in module_defs.get(module_name, [])
        )

    top_modules = {
        name
        for name, type_name in module_defs["Top"]
        if type_name in module_defs
        and type_name != "Footprints"
        and has_physical_component(type_name)
    }
    inventory: set[str] = set()

    def visit(module_name: str, prefix: str, active: tuple[str, ...]) -> None:
        if module_name in active:
            raise GateError(
                "cycle in Atopile module declarations: "
                + " -> ".join((*active, module_name))
            )
        for name, type_name in module_defs.get(module_name, []):
            path = f"{prefix}.{name}" if prefix else name
            if type_name in module_defs:
                visit(type_name, path, (*active, module_name))
            elif type_name in component_types:
                inventory.add(path)

    visit("Top", "", ())
    if not inventory:
        raise GateError(f"Atopile source yielded no physical components under {src_dir}")
    return top_modules, inventory


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

    board_interface_raw = data.get("board_interface")
    board_interface: BoardInterface | None = None
    if board_interface_raw is not None:
        if not isinstance(board_interface_raw, dict):
            raise GateError("'board_interface' must be a mapping if present")

        def _required_text(key: str) -> str:
            value = board_interface_raw.get(key)
            if not isinstance(value, str) or not value.strip():
                raise GateError(f"board_interface.{key} must be a non-empty string")
            return value.strip()

        power_board = _required_text("power_board")
        control_board = _required_text("control_board")
        if power_board == control_board:
            raise GateError("board_interface power_board and control_board must differ")
        connector = _required_text("connector")
        name = _required_text("name")

        nets_raw = board_interface_raw.get("nets")
        if not isinstance(nets_raw, list) or not nets_raw:
            raise GateError("board_interface.nets must be a non-empty list")
        if any(not isinstance(net, str) or not net.strip() for net in nets_raw):
            raise GateError("board_interface.nets must contain non-empty strings")
        nets = tuple(net.strip() for net in nets_raw)
        if len(set(nets)) != len(nets):
            raise GateError("board_interface.nets must not contain duplicates")

        allowed_raw = board_interface_raw.get("allowed_domains")
        if not isinstance(allowed_raw, list) or not allowed_raw:
            raise GateError("board_interface.allowed_domains must be a non-empty list")
        if any(not isinstance(domain, str) or not domain.strip() for domain in allowed_raw):
            raise GateError("board_interface.allowed_domains must contain non-empty strings")
        allowed_domains = tuple(domain.strip() for domain in allowed_raw)
        if len(set(allowed_domains)) != len(allowed_domains):
            raise GateError("board_interface.allowed_domains must not contain duplicates")
        unknown_domains = set(allowed_domains) - set(domains)
        if unknown_domains:
            raise GateError(
                "board_interface.allowed_domains names undeclared domain(s): "
                f"{sorted(unknown_domains)}"
            )

        # A plain list of names is insufficient for a board split: it cannot
        # answer which side owns a conductor, what its return reference is, or
        # what a fault/open harness must do.  Keep the old ``nets`` projection
        # for the compiled-net check, but require the typed signal records for
        # the production contract.  Values may be unresolved only when the
        # record says so; this is how an incomplete design stays visible and
        # fail-closed instead of acquiring an invented default.
        signals_raw = board_interface_raw.get("signals")
        if not isinstance(signals_raw, list) or not signals_raw:
            raise GateError(
                "board_interface.signals must be a non-empty list of typed "
                "signal records"
            )
        allowed_roles = {"return", "supply", "control", "telemetry", "fault"}
        allowed_owners = {
            "POWER_BOARD",
            "CONTROL_BOARD",
            "SHARED_REFERENCE",
            "UNRESOLVED",
        }
        allowed_directions = {
            "POWER_BOARD_TO_CONTROL_BOARD",
            "CONTROL_BOARD_TO_POWER_BOARD",
            "BIDIRECTIONAL",
            "RETURN",
            "UNRESOLVED",
        }
        allowed_statuses = {"resolved", "unresolved", "deferred"}
        signals: list[BoardInterfaceSignal] = []
        signal_names: list[str] = []
        required_signal_keys = {
            "net",
            "role",
            "owner",
            "direction",
            "domain",
            "return_net",
            "fault_behavior",
            "status",
        }
        for raw_signal in signals_raw:
            if not isinstance(raw_signal, dict):
                raise GateError(
                    "board_interface.signals entries must be mappings"
                )
            unknown_keys = set(raw_signal) - required_signal_keys
            missing_keys = required_signal_keys - set(raw_signal)
            if unknown_keys or missing_keys:
                detail = []
                if unknown_keys:
                    detail.append(f"unknown keys {sorted(unknown_keys)}")
                if missing_keys:
                    detail.append(f"missing keys {sorted(missing_keys)}")
                raise GateError(
                    "board_interface.signals entry has invalid schema: "
                    + "; ".join(detail)
                )

            net = raw_signal["net"]
            role = raw_signal["role"]
            owner = raw_signal["owner"]
            direction = raw_signal["direction"]
            domain = raw_signal["domain"]
            return_net = raw_signal["return_net"]
            fault_behavior = raw_signal["fault_behavior"]
            status = raw_signal["status"]
            if not isinstance(net, str) or not net.strip():
                raise GateError("board_interface.signals.net must be non-empty text")
            net = net.strip()
            if net in signal_names:
                raise GateError(
                    f"board_interface.signals repeats net {net!r}"
                )
            if net not in nets:
                raise GateError(
                    f"board_interface signal {net!r} is not listed in "
                    "board_interface.nets"
                )
            if not isinstance(role, str) or role not in allowed_roles:
                raise GateError(
                    f"board_interface signal {net!r} has invalid role {role!r}"
                )
            if owner is not None and (
                not isinstance(owner, str) or owner not in allowed_owners
            ):
                raise GateError(
                    f"board_interface signal {net!r} has invalid owner {owner!r}"
                )
            if direction is not None and (
                not isinstance(direction, str) or direction not in allowed_directions
            ):
                raise GateError(
                    f"board_interface signal {net!r} has invalid direction "
                    f"{direction!r}"
                )
            if not isinstance(domain, str) or not domain.strip():
                raise GateError(
                    f"board_interface signal {net!r} must declare a domain"
                )
            domain = domain.strip()
            if domain not in domains:
                raise GateError(
                    f"board_interface signal {net!r} names undeclared domain "
                    f"{domain!r}"
                )
            if net_owner.get(net) != domain:
                raise GateError(
                    f"board_interface signal {net!r} declares domain {domain!r}, "
                    f"but the manifest assigns it to {net_owner.get(net)!r}"
                )
            if return_net is not None and (
                not isinstance(return_net, str) or not return_net.strip()
            ):
                raise GateError(
                    f"board_interface signal {net!r} has invalid return_net"
                )
            if return_net is not None:
                return_net = return_net.strip()
                if return_net not in net_owner:
                    raise GateError(
                        f"board_interface signal {net!r} return_net {return_net!r} "
                        "is not a declared domain net"
                    )
                if net_owner[return_net] not in allowed_domains:
                    raise GateError(
                        f"board_interface signal {net!r} return_net {return_net!r} "
                        f"is outside allowed domains {list(allowed_domains)!r}"
                    )
            if fault_behavior is not None and (
                not isinstance(fault_behavior, str) or not fault_behavior.strip()
            ):
                raise GateError(
                    f"board_interface signal {net!r} has invalid fault_behavior"
                )
            if not isinstance(status, str) or status not in allowed_statuses:
                raise GateError(
                    f"board_interface signal {net!r} has invalid status {status!r}"
                )
            if status == "resolved" and any(
                value is None or (isinstance(value, str) and not value.strip())
                for value in (owner, direction, return_net, fault_behavior)
            ):
                raise GateError(
                    f"board_interface signal {net!r} is resolved but has "
                    "an incomplete owner/direction/return/fault contract"
                )
            if status == "resolved" and any(
                isinstance(value, str) and value == "UNRESOLVED"
                for value in (owner, direction, return_net, fault_behavior)
            ):
                raise GateError(
                    f"board_interface signal {net!r} is resolved but uses the "
                    "UNRESOLVED sentinel"
                )
            if status == "resolved":
                expected = {
                    "return": ("SHARED_REFERENCE", "RETURN"),
                    "supply": (power_board, "POWER_BOARD_TO_CONTROL_BOARD"),
                    "control": (control_board, "CONTROL_BOARD_TO_POWER_BOARD"),
                    "telemetry": (power_board, "POWER_BOARD_TO_CONTROL_BOARD"),
                    "fault": (control_board, "CONTROL_BOARD_TO_POWER_BOARD"),
                }[role]
                if (owner, direction) != expected:
                    raise GateError(
                        f"board_interface signal {net!r} has incoherent "
                        f"role/owner/direction: role {role!r} requires "
                        f"owner {expected[0]!r} and direction {expected[1]!r}"
                    )
                if role == "return" and return_net != net:
                    raise GateError(
                        f"board_interface return signal {net!r} must return to itself"
                    )
            if status != "resolved" and owner is None and direction is None:
                # Explicitly unresolved is valid; the readiness check below
                # will keep generation blocked until the missing decision is
                # filled in.
                pass
            signal_names.append(net)
            signals.append(
                BoardInterfaceSignal(
                    net=net,
                    role=role,
                    owner=owner,
                    direction=direction,
                    domain=domain,
                    return_net=return_net,
                    fault_behavior=fault_behavior,
                    status=status,
                )
            )
        if tuple(signal_names) != nets:
            raise GateError(
                "board_interface.signals nets must exactly match board_interface.nets "
                "in the same order"
            )

        def _mapping(key: str) -> dict[str, Any]:
            value = board_interface_raw.get(key)
            if not isinstance(value, dict):
                raise GateError(f"board_interface.{key} must be a mapping")
            return dict(value)

        safety_target = _mapping("safety_target")
        if safety_target.get("pollution_degree") != 3:
            raise GateError(
                "board_interface.safety_target.pollution_degree must be 3 "
                "for the approved split-board contract"
            )
        if safety_target.get("reinforced_creepage_mm") != 12.6:
            raise GateError(
                "board_interface.safety_target.reinforced_creepage_mm must be "
                "12.6 for the approved split-board contract"
            )
        if not isinstance(safety_target.get("standard"), str) or not safety_target[
            "standard"
        ].strip():
            raise GateError("board_interface.safety_target.standard must be non-empty text")

        connector_spec = _mapping("connector_spec")
        mechanical_spec = _mapping("mechanical_spec")
        generation_spec = _mapping("generation")
        fault_aggregation = _mapping("fault_aggregation")
        if fault_aggregation.get("output_net") not in nets:
            raise GateError(
                "board_interface.fault_aggregation.output_net must name one "
                "of board_interface.nets"
            )
        if fault_aggregation.get("active_level") not in {"high", "low"}:
            raise GateError(
                "board_interface.fault_aggregation.active_level must be 'high' or 'low'"
            )
        if not isinstance(fault_aggregation.get("latched"), bool):
            raise GateError(
                "board_interface.fault_aggregation.latched must be boolean"
            )
        sources = fault_aggregation.get("sources")
        if not isinstance(sources, list) or not sources or any(
            not isinstance(source, str) or not source.strip() for source in sources
        ):
            raise GateError(
                "board_interface.fault_aggregation.sources must be a non-empty "
                "list of names"
            )
        if fault_aggregation.get("status") not in {"resolved", "unresolved"}:
            raise GateError(
                "board_interface.fault_aggregation.status must be resolved or unresolved"
            )
        if generation_spec.get("status") not in {"blocked", "ready"}:
            raise GateError(
                "board_interface.generation.status must be 'blocked' or 'ready'"
            )
        required_fields = generation_spec.get("required_fields")
        if not isinstance(required_fields, list) or not required_fields or any(
            not isinstance(path, str) or not path.strip() for path in required_fields
        ):
            raise GateError(
                "board_interface.generation.required_fields must be a non-empty "
                "list of field paths"
            )
        if len(set(required_fields)) != len(required_fields):
            raise GateError(
                "board_interface.generation.required_fields must not contain duplicates"
            )
        if set(required_fields) != MANDATORY_GENERATION_REQUIRED_FIELDS:
            missing = sorted(MANDATORY_GENERATION_REQUIRED_FIELDS - set(required_fields))
            extra = sorted(set(required_fields) - MANDATORY_GENERATION_REQUIRED_FIELDS)
            raise GateError(
                "board_interface.generation.required_fields must be exactly the "
                f"mandatory readiness set; missing={missing}, extra={extra}"
            )

        deferred_raw = board_interface_raw.get("deferred_signals", [])
        if not isinstance(deferred_raw, list):
            raise GateError("board_interface.deferred_signals must be a list")
        deferred_signals: list[dict[str, Any]] = []
        deferred_names: set[str] = set()
        for entry in deferred_raw:
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
                raise GateError(
                    "board_interface.deferred_signals entries must map a name"
                )
            name_value = entry["name"].strip()
            if not name_value or name_value in deferred_names or name_value in signal_names:
                raise GateError(
                    f"board_interface.deferred_signals repeats or conflicts with "
                    f"an interface name: {name_value!r}"
                )
            if entry.get("status") not in {"deferred", "not_present", "unresolved"}:
                raise GateError(
                    f"board_interface.deferred_signals entry {name_value!r} "
                    "must be explicitly deferred, not_present, or unresolved"
                )
            deferred_names.add(name_value)
            deferred_signals.append(dict(entry))

        board_interface = BoardInterface(
            name=name,
            power_board=power_board,
            control_board=control_board,
            connector=connector,
            nets=nets,
            allowed_domains=allowed_domains,
            signals=tuple(signals),
            safety_target=safety_target,
            connector_spec=connector_spec,
            mechanical_spec=mechanical_spec,
            generation_spec=generation_spec,
            fault_aggregation=fault_aggregation,
            deferred_signals=tuple(deferred_signals),
        )

    board_partition_raw = data.get("board_partition")
    board_partition: BoardPartition | None = None
    if board_partition_raw is not None:
        if not isinstance(board_partition_raw, dict):
            raise GateError("'board_partition' must be a mapping if present")
        status = board_partition_raw.get("status")
        if status != "planned":
            raise GateError(
                "board_partition.status must be 'planned' until two physical "
                "board artifacts and their migration gates exist"
            )
        if board_interface is None:
            raise GateError(
                "board_partition requires board_interface so its board names "
                "and cross-board nets have one explicit contract"
            )

        boards_raw = board_partition_raw.get("boards")
        if not isinstance(boards_raw, dict) or len(boards_raw) != 2:
            raise GateError("board_partition.boards must contain exactly two boards")
        board_domains: dict[str, str] = {}
        modules: dict[str, tuple[str, ...]] = {}
        components: dict[str, tuple[str, ...]] = {}
        seen_modules: set[str] = set()
        seen_components: set[str] = set()
        for board_name, body in boards_raw.items():
            if not isinstance(board_name, str) or not board_name.strip():
                raise GateError("board_partition board names must be non-empty strings")
            if not isinstance(body, dict):
                raise GateError(f"board_partition board {board_name!r} must be a mapping")
            domain = body.get("domain")
            if not isinstance(domain, str) or domain not in domains:
                raise GateError(
                    f"board_partition board {board_name!r} must name one declared "
                    f"domain, got {domain!r}"
                )
            paths_raw = body.get("modules")
            if not isinstance(paths_raw, list) or not paths_raw:
                raise GateError(
                    f"board_partition board {board_name!r} must declare a non-empty "
                    "modules list"
                )
            paths = tuple(str(path) for path in paths_raw)
            if any(not path.strip() for path in paths) or len(set(paths)) != len(paths):
                raise GateError(
                    f"board_partition board {board_name!r} modules must be unique "
                    "non-empty paths"
                )
            overlap = seen_modules & set(paths)
            if overlap:
                raise GateError(
                    "board_partition module path(s) assigned to more than one "
                    f"board: {sorted(overlap)}"
                )
            seen_modules.update(paths)
            board_domains[board_name] = domain
            modules[board_name] = paths
            components_raw = body.get("components")
            if not isinstance(components_raw, list) or not components_raw:
                raise GateError(
                    f"board_partition board {board_name!r} must declare a non-empty "
                    "exact components list"
                )
            component_paths = tuple(components_raw)
            if any(
                not isinstance(path, str) or not path.strip()
                for path in component_paths
            ) or len(set(component_paths)) != len(component_paths):
                raise GateError(
                    f"board_partition board {board_name!r} components must be "
                    "unique non-empty paths"
                )
            overlap = seen_components & set(component_paths)
            if overlap:
                raise GateError(
                    "board_partition component path(s) assigned to more than one "
                    f"board: {sorted(overlap)}"
                )
            seen_components.update(component_paths)
            components[board_name] = component_paths

        power_board = board_interface.power_board
        control_board = board_interface.control_board
        if set(board_domains) != {power_board, control_board}:
            raise GateError(
                "board_partition.boards must match board_interface.power_board "
                "and board_interface.control_board exactly"
            )
        if board_domains[power_board] == board_domains[control_board]:
            raise GateError("power and control boards must own different domains")
        if board_domains[power_board] != "HV" or board_domains[control_board] != "SELV":
            raise GateError(
                "split-board partition must assign HV to the power board and "
                "SELV to the control board"
            )

        cross_modules_raw = board_partition_raw.get("cross_domain_modules")
        if not isinstance(cross_modules_raw, list) or not cross_modules_raw:
            raise GateError(
                "board_partition.cross_domain_modules must be a non-empty list"
            )
        cross_modules = tuple(cross_modules_raw)
        if any(not isinstance(path, str) or not path.strip() for path in cross_modules):
            raise GateError(
                "board_partition.cross_domain_modules must contain non-empty names"
            )
        if len(set(cross_modules)) != len(cross_modules):
            raise GateError("board_partition.cross_domain_modules must be unique")

        cross_components_raw = board_partition_raw.get("cross_domain_components")
        if not isinstance(cross_components_raw, list) or not cross_components_raw:
            raise GateError(
                "board_partition.cross_domain_components must be a non-empty list"
            )
        cross_components: list[dict[str, Any]] = []
        for entry in cross_components_raw:
            if not isinstance(entry, dict):
                raise GateError(
                    "board_partition.cross_domain_components entries must be mappings"
                )
            path = entry.get("instance_path")
            module = entry.get("module")
            sides = entry.get("sides")
            if not isinstance(path, str) or not path.strip():
                raise GateError(
                    "board_partition cross-domain component requires instance_path"
                )
            if not isinstance(module, str) or not module.strip():
                raise GateError(
                    f"board_partition cross-domain component {path!r} requires module"
                )
            if path in seen_components:
                raise GateError(
                    f"board_partition component {path!r} is assigned both to a board "
                    "and to cross-domain ownership"
                )
            if not isinstance(sides, dict) or not sides:
                raise GateError(
                    f"board_partition cross-domain component {path!r} requires "
                    "a non-empty sides mapping"
                )
            side_names = set(sides)
            if not side_names <= set(board_domains):
                raise GateError(
                    f"board_partition cross-domain component {path!r} names "
                    f"unknown board side(s): {sorted(side_names - set(board_domains))}"
                )
            for board_name, groups in sides.items():
                if not isinstance(groups, list) or not groups or any(
                    not isinstance(group, str) or not group.strip() for group in groups
                ):
                    raise GateError(
                        f"board_partition cross-domain component {path!r} side "
                        f"{board_name!r} must contain non-empty group names"
                    )
            cross_components.append(
                {
                    "instance_path": path.strip(),
                    "module": module.strip(),
                    "sides": {
                        str(board): tuple(str(group).strip() for group in groups)
                        for board, groups in sides.items()
                    },
                }
            )
            seen_components.add(path)
        if len({entry["instance_path"] for entry in cross_components}) != len(cross_components):
            raise GateError(
                "board_partition.cross_domain_components must not repeat paths"
            )

        sides_raw = board_partition_raw.get("isolator_sides")
        if not isinstance(sides_raw, list) or not sides_raw:
            raise GateError("board_partition.isolator_sides must be a non-empty list")
        isolator_by_path = {iso.instance_path: iso for iso in isolators}
        seen_side_paths: set[str] = set()
        isolator_sides: list[IsolatorBoardSides] = []
        for entry in sides_raw:
            if not isinstance(entry, dict):
                raise GateError("board_partition isolator_sides entries must be mappings")
            path = entry.get("instance_path")
            power_group = entry.get("power_board_group")
            control_group = entry.get("control_board_group")
            if not all(isinstance(value, str) and value.strip() for value in (path, power_group, control_group)):
                raise GateError(
                    "board_partition isolator_sides entries require non-empty "
                    "instance_path, power_board_group, and control_board_group"
                )
            if path in seen_side_paths:
                raise GateError(f"duplicate board isolator side mapping: {path!r}")
            seen_side_paths.add(path)
            iso = isolator_by_path.get(path)
            if iso is None:
                raise GateError(
                    f"board_partition isolator {path!r} is not declared under isolators"
                )
            if power_group not in iso.groups or control_group not in iso.groups:
                raise GateError(
                    f"board_partition isolator {path!r} names unknown group(s): "
                    f"{power_group!r}, {control_group!r}"
                )
            if power_group == control_group:
                raise GateError(
                    f"board_partition isolator {path!r} maps both boards to "
                    f"the same group {power_group!r}"
                )
            if {power_group, control_group} != set(iso.groups):
                raise GateError(
                    f"board_partition isolator {path!r} must map every group "
                    f"exactly once; declared groups are {sorted(iso.groups)!r}, "
                    f"mapped groups are {sorted((power_group, control_group))!r}"
                )
            isolator_sides.append(
                IsolatorBoardSides(
                    instance_path=path,
                    power_board_group=power_group,
                    control_board_group=control_group,
                )
            )
        declared_paths = set(isolator_by_path)
        if seen_side_paths != declared_paths:
            raise GateError(
                "board_partition.isolator_sides must cover every declared isolator; "
                f"missing: {sorted(declared_paths - seen_side_paths)}"
            )

        side_by_path = {entry.instance_path: entry for entry in isolator_sides}
        isolator_paths = set(isolator_by_path)
        cross_paths: set[str] = set()
        for entry in cross_components:
            path = entry["instance_path"]
            if path in cross_paths:
                raise GateError(
                    f"board_partition.cross_domain_components repeats {path!r}"
                )
            cross_paths.add(path)
            if entry["module"] not in set(modules[power_board]) | set(
                modules[control_board]
            ) | set(cross_modules):
                raise GateError(
                    f"board_partition cross-domain component {path!r} names "
                    f"module {entry['module']!r} that is not in the partition"
                )
            mapped_sides = entry["sides"]
            iso_side = side_by_path.get(path)
            if path not in isolator_paths and entry["module"] not in cross_modules:
                raise GateError(
                    f"board_partition non-isolator cross-domain component {path!r} "
                    f"must belong to cross_domain_modules, got module "
                    f"{entry['module']!r}"
                )
            if iso_side is not None:
                expected = {
                    power_board: (iso_side.power_board_group,),
                    control_board: (iso_side.control_board_group,),
                }
                if mapped_sides != expected:
                    raise GateError(
                        f"board_partition cross-domain isolator {path!r} sides "
                        "must exactly match isolator_sides"
                    )
            elif len(mapped_sides) != 1 or next(iter(mapped_sides.values())) != ("all",):
                raise GateError(
                    f"board_partition cross-domain component {path!r} is not an "
                    "isolator and must have exactly one board side named 'all'"
                )
        if not cross_paths:
            raise GateError("board_partition.cross_domain_components is empty")

        board_partition = BoardPartition(
            status=status,
            power_board=power_board,
            control_board=control_board,
            board_domains=board_domains,
            modules=modules,
            components=components,
            cross_domain_components=tuple(cross_components),
            isolator_sides=tuple(isolator_sides),
            cross_domain_modules=cross_modules,
        )

    return Manifest(
        domains=domains,
        isolators=isolators,
        chains=chains,
        board_interface=board_interface,
        board_partition=board_partition,
    )


def check_board_interface_contract(
    netlist: Netlist, manifest: Manifest
) -> list[str]:
    """Verify that every planned board-to-board net is explicitly SELV-only.

    A missing interface net is a gate error: it means the contract no longer
    describes the compiled design.  A net assigned to a disallowed domain is a
    real violation: it would put HV or an unclassified crossing on the board
    connector.  The function returns violations so the existing gate keeps its
    normal non-zero verdict and GitHub summary behavior.
    """
    interface = manifest.board_interface
    if interface is None:
        return []

    compiled_names = set(netlist.nets.values())
    missing = sorted(set(interface.nets) - compiled_names)
    if missing:
        raise GateError(
            f"board_interface {interface.name!r} names net(s) absent from the "
            f"compiled netlist: {missing} -- the connector contract is stale"
        )

    owners = {
        net: domain
        for domain, nets in manifest.domains.items()
        for net in nets
    }
    violations: list[str] = []
    for net in interface.nets:
        owner = owners.get(net)
        if owner is None:
            violations.append(
                f"board-interface net {net!r} has no declared safety domain"
            )
        elif owner not in interface.allowed_domains:
            violations.append(
                f"board-interface net {net!r} is classified as {owner!r}, "
                f"outside allowed domains {list(interface.allowed_domains)!r}"
            )
    return violations


def validate_split_domain_contract(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    src_dir: Path | None = None,
    netlist_path: Path | None = None,
) -> Manifest:
    """Load and fully validate the source-backed split-board domain contract.

    This is the public authority for consumers that need to decide whether a
    split-board operation may proceed.  Keeping the call here is deliberate:
    :func:`load_manifest` owns typed signal semantics and the mandatory
    generation-field set, while :func:`check_board_partition_contract` owns
    the exact source component/module inventory.  A readiness consumer must
    not reproduce either rule with a second YAML parser or a regex.

    ``src_dir`` defaults to the sibling ``src`` directory of the supplied
    domain manifest.  Tests and callers using a copied manifest can provide
    the hierarchy's actual source directory explicitly.  ``netlist_path`` is
    optional because the future split contract is valid before a freshly
    compiled legacy netlist exists; when supplied, the same board-interface
    and partition checks are also applied to that compiled netlist.

    A malformed contract or an inventory mismatch raises :class:`GateError`.
    A structurally valid but generation-incomplete contract is returned so
    the readiness layer can report its blockers (unresolved signals,
    connector decisions, and mechanical decisions) without treating them as
    malformed input.
    """
    manifest = load_manifest(manifest_path)
    if manifest.board_interface is None:
        raise GateError("split-board domain contract has no board_interface")
    if manifest.board_partition is None:
        raise GateError("split-board domain contract has no board_partition")

    resolved_src_dir = src_dir if src_dir is not None else manifest_path.parent / "src"
    netlist = parse_netlist(netlist_path) if netlist_path is not None else None
    interface_violations = (
        check_board_interface_contract(netlist, manifest)
        if netlist is not None
        else []
    )
    partition_violations = check_board_partition_contract(
        manifest, netlist=netlist, src_dir=resolved_src_dir
    )
    violations = [*interface_violations, *partition_violations]
    if violations:
        raise GateError(
            "split-board domain contract has violations: "
            + "; ".join(violations)
        )
    return manifest


def check_board_interface_generation_ready(manifest: Manifest) -> None:
    """Fail closed until the approved split can be rendered into boards.

    The interface contract is useful before a connector or floorplan exists,
    so the ordinary domain gate intentionally checks only its electrical
    boundary.  A split-board generator must call this stricter readiness
    check.  It rejects unresolved signal semantics and every missing
    connector/mechanical field named by ``generation.required_fields``;
    ``None`` is an honest design blocker, never a default part or geometry.
    """
    interface = manifest.board_interface
    if interface is None:
        raise GateError(
            "board-interface generation is blocked: manifest has no board_interface"
        )

    blockers: list[str] = []
    unresolved = [signal.net for signal in interface.signals if signal.status != "resolved"]
    if unresolved:
        blockers.append(
            "unresolved signal semantics: " + ", ".join(sorted(unresolved))
        )
    outside_domains = [
        signal.net
        for signal in interface.signals
        if signal.domain not in interface.allowed_domains
    ]
    if outside_domains:
        blockers.append(
            "interface signals outside allowed domains "
            f"{list(interface.allowed_domains)!r}: {', '.join(sorted(outside_domains))}"
        )
    if interface.fault_aggregation.get("status") != "resolved":
        blockers.append("fault aggregation semantics are unresolved")

    roots: dict[str, Any] = {
        "safety_target": interface.safety_target,
        "connector_spec": interface.connector_spec,
        "mechanical_spec": interface.mechanical_spec,
        "generation": interface.generation_spec,
    }

    def _lookup(path: str) -> Any:
        value: Any = roots
        for component in path.split("."):
            if not isinstance(value, dict) or component not in value:
                return None
            value = value[component]
        return value

    for path in interface.generation_spec.get("required_fields", []):
        value = _lookup(path)
        if value is None or value == "" or value == [] or value == {}:
            blockers.append(f"missing required field: {path}")

    if interface.generation_spec.get("status") != "ready":
        blockers.append(
            "generation.status is not 'ready' (connector, pinout, and mechanical "
            "partition remain unresolved)"
        )
    if blockers:
        raise GateError(
            "board-interface generation blocked until the approved contract is "
            "complete: " + "; ".join(blockers)
        )


def check_board_partition_contract(
    manifest: Manifest,
    netlist: Netlist | None = None,
    src_dir: Path | None = None,
) -> list[str]:
    """Return violations in the planned split-board ownership contract.

    The parser enforces structural validity and complete isolator-side
    coverage.  This check supplies the small semantic part that is useful to
    the existing gate: the board-to-board interface must remain wholly on
    the control-side (SELV) domain.  It deliberately does not inspect the
    legacy netlist for physical board placement; ``status: planned`` means
    that claim belongs to the future two-PCB migration gate.
    """
    partition = manifest.board_partition
    if partition is None:
        return []
    interface = manifest.board_interface
    if interface is None:  # defensive; load_manifest rejects this combination
        return ["board partition has no board-interface contract"]
    control_domain = partition.board_domains[partition.control_board]
    owners = {
        net: domain
        for domain, nets in manifest.domains.items()
        for net in nets
    }
    violations: list[str] = []
    for net in interface.nets:
        if owners.get(net) != control_domain:
            violations.append(
                f"split-board interface net {net!r} is not owned by the "
                f"control-board domain {control_domain!r}"
            )

    # Ownership is an exact inventory, not a module-name convention.  When
    # source is supplied (the production gate always supplies it), derive the
    # physical leaf instances from Top and require every one to be accounted
    # for exactly once.  This catches a newly-added component before a future
    # board generator can silently drop it.
    if src_dir is not None:
        source_modules, source_components = _source_component_inventory(src_dir)
        declared_modules = set().union(*partition.modules.values()) | set(
            partition.cross_domain_modules
        )
        if declared_modules != source_modules:
            missing = sorted(source_modules - declared_modules)
            extra = sorted(declared_modules - source_modules)
            raise GateError(
                "board_partition module inventory is not source-backed: "
                f"missing={missing}, extra={extra}"
            )
        declared_components = set().union(*partition.components.values()) | {
            entry["instance_path"] for entry in partition.cross_domain_components
        }
        if declared_components != source_components:
            missing = sorted(source_components - declared_components)
            extra = sorted(declared_components - source_components)
            raise GateError(
                "board_partition component inventory is not source-backed: "
                f"missing={missing}, extra={extra}"
            )
        for board_name, paths in partition.components.items():
            allowed_roots = set(partition.modules[board_name])
            bad = sorted(
                path for path in paths if path.split(".", 1)[0] not in allowed_roots
            )
            if bad:
                raise GateError(
                    f"board_partition board {board_name!r} owns components outside "
                    f"its modules: {bad}"
                )
        for entry in partition.cross_domain_components:
            root = entry["instance_path"].split(".", 1)[0]
            if root != entry["module"]:
                raise GateError(
                    f"board_partition component {entry['instance_path']!r} is not "
                    f"under its declared module {entry['module']!r}"
                )

    if netlist is not None:
        compiled_components = {component.instance_path for component in netlist.components.values()}
        declared_components = set().union(*partition.components.values()) | {
            entry["instance_path"] for entry in partition.cross_domain_components
        }
        if compiled_components != declared_components:
            missing = sorted(compiled_components - declared_components)
            extra = sorted(declared_components - compiled_components)
            raise GateError(
                "board_partition component inventory does not match compiled "
                f"netlist: missing={missing}, extra={extra}"
            )
        owners = {
            net: domain
            for domain, nets in manifest.domains.items()
            for net in nets
        }
        path_to_refs: dict[str, list[str]] = {}
        for ref, component in netlist.components.items():
            path_to_refs.setdefault(component.instance_path, []).append(ref)
        isolator_by_path = {iso.instance_path: iso for iso in manifest.isolators}
        for side in partition.isolator_sides:
            iso = isolator_by_path[side.instance_path]
            refs = path_to_refs.get(side.instance_path, [])
            if len(refs) != 1:
                raise GateError(
                    f"board_partition isolator {side.instance_path!r} does not "
                    "resolve to exactly one compiled component"
                )
            ref = refs[0]
            for board_name, group_name in (
                (partition.power_board, side.power_board_group),
                (partition.control_board, side.control_board_group),
            ):
                group_nets = {
                    netlist.nets[netlist.pin_net[(ref, pin)]]
                    for pin in iso.groups[group_name]
                }
                group_domains = {owners.get(net) for net in group_nets}
                if None in group_domains:
                    raise GateError(
                        f"board_partition isolator {side.instance_path!r} group "
                        f"{group_name!r} contains unclassified net(s): "
                        f"{sorted(net for net in group_nets if net not in owners)}"
                    )
                expected_domain = partition.board_domains[board_name]
                if group_domains != {expected_domain}:
                    violations.append(
                        f"isolator {side.instance_path!r} group {group_name!r} "
                        f"is classified as {sorted(group_domains)!r}, expected "
                        f"board domain {expected_domain!r}"
                    )
    return violations


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

    def without_labels(self, labels: set[str]) -> Graph:
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

    dist: dict[str, int] = dict.fromkeys(sorted(sources), 0)
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


def run(
    netlist_path: Path,
    manifest_path: Path,
    src_dir: Path,
    skip_freshness: bool = False,
    require_generation_ready: bool = False,
) -> int:
    try:
        if not skip_freshness:
            check_netlist_freshness(netlist_path, src_dir)
        netlist = parse_netlist(netlist_path)
        manifest = load_manifest(manifest_path)
        if require_generation_ready:
            check_board_interface_generation_ready(manifest)
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
        board_interface_violations = check_board_interface_contract(netlist, manifest)
        board_partition_violations = check_board_partition_contract(
            manifest, netlist=netlist, src_dir=src_dir
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
    if manifest.board_interface is not None:
        interface = manifest.board_interface
        print(
            f"Board interface {interface.name!r}: "
            f"{interface.power_board} <-> {interface.control_board}, "
            f"connector {interface.connector!r}, "
            f"{len(interface.nets)} SELV-contract net(s)."
        )
    if manifest.board_partition is not None:
        partition = manifest.board_partition
        print(
            f"Split-board partition ({partition.status}): "
            f"{partition.power_board}=HV, {partition.control_board}=SELV, "
            f"{len(partition.isolator_sides)} isolator-side mapping(s)."
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

    if (
        not domain_violations
        and not isolator_violations
        and not chain_violations
        and not board_interface_violations
        and not board_partition_violations
    ):
        print(
            "\nPASSED -- 0 domain crossings, 0 isolator-barrier breaches, "
            "0 protective-impedance chain defects, "
            "0 board-interface contract violations"
        )
        if gh:
            with open(gh, "a") as f:
                f.write("### Netlist Domain-Partition Gate -- PASSED\n")
                f.write(
                    f"0 violations across {len(manifest.domains)} domains, "
                    f"{len(ref_isolator)} isolators, "
                    f"{len(manifest.chains)} protective-impedance chains, "
                    f"{len(board_interface_violations)} board-interface "
                    f"contract violation(s), {len(board_partition_violations)} "
                    "split-board partition violation(s).\n"
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

    print(
        f"\n=== BOARD-INTERFACE CONTRACT VIOLATIONS: "
        f"{len(board_interface_violations)} ==="
        if board_interface_violations
        else "\n=== BOARD-INTERFACE CONTRACT VIOLATIONS: 0 ==="
    )
    for detail in board_interface_violations:
        print(f"\n  {detail}")
        gh_lines.append(f"- board-interface: {detail}")

    print(
        f"\n=== SPLIT-BOARD PARTITION VIOLATIONS: "
        f"{len(board_partition_violations)} ==="
        if board_partition_violations
        else "\n=== SPLIT-BOARD PARTITION VIOLATIONS: 0 ==="
    )
    for detail in board_partition_violations:
        print(f"\n  {detail}")
        gh_lines.append(f"- split-board partition: {detail}")

    if gh:
        with open(gh, "a") as f:
            f.write("### Netlist Domain-Partition Gate -- FAILED\n")
            f.write(
                f"{len(domain_violations)} domain violation(s), "
                f"{len(isolator_violations)} isolator violation(s), "
                f"{len(chain_violations)} protective-impedance chain "
                f"violation(s), {len(board_interface_violations)} "
                f"board-interface contract violation(s), "
                f"{len(board_partition_violations)} split-board partition "
                "violation(s)\n\n"
            )
            for line in gh_lines:
                f.write(line + "\n")

    print(
        f"\nFAILED -- {len(domain_violations)} domain violation(s), "
        f"{len(isolator_violations)} isolator barrier violation(s), "
        f"{len(chain_violations)} protective-impedance chain violation(s), "
        f"{len(board_interface_violations)} board-interface contract "
        f"violation(s), {len(board_partition_violations)} split-board "
        "partition violation(s)"
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
    parser.add_argument(
        "--require-generation-ready",
        action="store_true",
        help=(
            "Fail closed unless connector, pinout, mechanical partition, "
            "and all typed signal semantics are resolved. Use before split-board generation."
        ),
    )
    args = parser.parse_args()
    sys.exit(
        run(
            args.netlist,
            args.manifest,
            args.src_dir,
            args.skip_freshness_check,
            args.require_generation_ready,
        )
    )


if __name__ == "__main__":
    main()
