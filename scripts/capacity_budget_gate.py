#!/usr/bin/env python3
"""Design-capacity budget CI gate: fan-in reachability on the fault tree.

Motivating incident (2026-07-26): two fully-designed protection circuits
(OCP-02, UVL-02) could not be wired into the safety-interlock fault latch
because every SET-path input on both `SN74HC4075` fan-in packages was
occupied or structurally unusable. Two independent agents each manually
searched the fault tree for a spare input and each concluded there was
none -- the second agent should not have had to search. See
docs/hardware/UVL02_DESIGN.md SS7/SS7.1 and docs/hardware/OCP02_DESIGN.md's
"Fault integration" section for the manual survey this gate automates.

This is a reachability question over the netlist graph, not a pin-
occupancy count. A naive "count unconnected pins" check on today's tree
would report four free inputs on `fault_any_or` and be wrong about all
four:
  - `fault_or.A3/B3/C3`   -- GND-tied, but their gate's Y3 drives nothing.
  - `fault_any_or.C1`     -- looked free to two surveys; already claimed
                             by THM-02 (commit d99c88e2) on the current
                             tree.
  - `fault_any_or.C2`     -- GND-tied and looks free, but this gate
                             computes the RESET qualifier; wiring a fault
                             here blocks reset without ever tripping the
                             latch.
  - `fault_any_or.A3/B3/C3` -- entirely unreferenced, but (like fault_or's
                             gate 3) the gate's own output has no path
                             into the SET aggregation.

An input is only "available" if a signal applied there reaches the
destination pin declared in `fault_tree.set_pin` (scripts/
capacity_budget_packages.yaml) via the fixed, already-built wiring of the
aggregator chain. This is computed by BFS over "gate edges": a directed
edge from an input pin's net to its gate's output pin's net, for every
instantiated fan-in package in `fault_tree.aggregator_mpns`.

Identity and connectivity are both read from elec/build/, which is built
by `make netlist` and is gitignored (never committed). Two inputs must be
trusted carefully:
  1. `elec/build/default.net`'s `(nets ...)` section (keyed on (ref, pin))
     is the trustworthy connectivity graph. Its `libsource`/`(comp ...)`
     part-identity fields are NOT trustworthy -- atopile's KiCad exporter
     aliases part identity by footprint (confirmed on this tree: U24, the
     real SN74HC00 latch, is mislabeled `libsource part "SN74HC4075DR"`
     because it shares the SOIC-14 footprint with U22/U23). Identity here
     instead comes from `elec/build/default.csv` (MPN grouping is by the
     real `mpn` field, not footprint) combined with `default.net`'s own
     `sheetpath` field (the atopile instance path, e.g. "safety.latch" --
     also unaffected by the footprint-aliasing bug, since it is written
     from the design hierarchy, not the KiCad symbol library lookup).
  2. Missing/empty netlist or BOM, a parse failure, or a `required_packages`
     entry absent from the design must fail closed (never report a clean
     pass on "nothing parsed").

Exit codes:
  0 - OK: report generated, no capacity_defect found.
  3 - capacity_defect: an aggregator gate has a real (non-GND, non-cascade)
      occupant driving one of its inputs, but that gate's own output net
      is a dead end (drives nothing). A fault source wired into a dead
      gate is a silent no-op -- always a bug, regardless of design intent,
      so this is the one condition this gate blocks a merge on.
  5 - tool_error: missing/empty/unparseable netlist or BOM, a
      required_packages entry with zero instances, or an internal
      assertion about the parsed structure failing. Never treated as "0
      violations".

Usage:
  uv run python scripts/capacity_budget_gate.py [--help]
  uv run python scripts/capacity_budget_gate.py --netlist PATH --bom PATH --config PATH
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from _lib.repo import find_repo_root  # noqa: E402
from _lib.github_summary import get_github_summary_path  # noqa: E402

REPO_ROOT = find_repo_root()
DEFAULT_NETLIST = REPO_ROOT / "elec" / "build" / "default.net"
DEFAULT_BOM = REPO_ROOT / "elec" / "build" / "default.csv"
DEFAULT_CONFIG = REPO_ROOT / "scripts" / "capacity_budget_packages.yaml"


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


# --------------------------------------------------------------------------
# Minimal S-expression parser for the KiCad-style netlist export.
#
# Written from scratch rather than regex/line-scanning specifically so the
# "(nets ...)" section is parsed by real nesting, not text patterns that
# could silently drift out of sync with reformatted output (this is the
# section the netlist caveat above says to trust).
# --------------------------------------------------------------------------


def _tokenize(text: str) -> list:
    tokens = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "()":
            tokens.append(c)
            i += 1
        elif c.isspace():
            i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                    continue
                buf.append(text[j])
                j += 1
            if j >= n:
                raise GateError("netlist parse error: unterminated quoted string")
            tokens.append(("str", "".join(buf)))
            i = j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "()":
                j += 1
            tokens.append(("atom", text[i:j]))
            i = j
    return tokens


def _parse_sexp(text: str) -> list:
    """Parse an S-expression document into nested Python lists."""
    tokens = _tokenize(text)
    pos = 0

    def parse_expr():
        nonlocal pos
        if pos >= len(tokens):
            raise GateError("netlist parse error: unexpected end of input")
        tok = tokens[pos]
        if tok == "(":
            pos += 1
            lst = []
            while pos < len(tokens) and tokens[pos] != ")":
                lst.append(parse_expr())
            if pos >= len(tokens):
                raise GateError("netlist parse error: unbalanced parentheses")
            pos += 1  # consume ')'
            return lst
        elif tok == ")":
            raise GateError("netlist parse error: unexpected ')'")
        else:
            pos += 1
            return tok[1]  # unwrap ('str', v) / ('atom', v)

    exprs = []
    while pos < len(tokens):
        exprs.append(parse_expr())
    return exprs


def _sexp_get(node: list, tag: str):
    """Return the first child sublist of `node` whose head == tag."""
    if not isinstance(node, list):
        return None
    for child in node:
        if isinstance(child, list) and child and child[0] == tag:
            return child
    return None


def _sexp_get_all(node: list, tag: str) -> list:
    if not isinstance(node, list):
        return []
    return [
        child
        for child in node
        if isinstance(child, list) and child and child[0] == tag
    ]


def _sexp_get_val(node: list, tag: str) -> str | None:
    child = _sexp_get(node, tag)
    if child is None or len(child) < 2:
        return None
    return child[1]


def _find_recursive(node, tag: str):
    """Depth-first search for the first sublist anywhere under `node` whose
    head == tag. Used to find "components"/"nets" regardless of exact
    top-level export structure.
    """
    if not isinstance(node, list):
        return None
    if node and node[0] == tag:
        return node
    for child in node:
        found = _find_recursive(child, tag)
        if found is not None:
            return found
    return None


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------


@dataclass
class Component:
    ref: str
    footprint: str
    instance_path: str  # from `sheetpath`, e.g. "safety.fault_or"


@dataclass
class Net:
    code: str
    name: str
    nodes: list  # list[(ref, pin)]


@dataclass
class Netlist:
    components: dict  # ref -> Component
    nets: dict  # code -> Net
    pin_to_net: dict  # (ref, pin) -> code

    def net_of(self, ref: str, pin: str) -> str | None:
        return self.pin_to_net.get((ref, pin))


def load_netlist(path: Path) -> Netlist:
    if not path.is_file():
        raise GateError(f"netlist not found: {path}")
    text = path.read_text()
    if not text.strip():
        raise GateError(f"netlist is empty: {path}")

    tree = _parse_sexp(text)
    if not tree:
        raise GateError(f"netlist parsed to nothing: {path}")

    export = tree[0] if isinstance(tree[0], list) else None
    if export is None or export[0] != "export":
        raise GateError(
            f"netlist does not start with an 'export' form (got {tree[0]!r}): {path}"
        )

    components_section = _find_recursive(export, "components")
    nets_section = _find_recursive(export, "nets")
    if components_section is None:
        raise GateError(f"netlist has no 'components' section: {path}")
    if nets_section is None:
        raise GateError(f"netlist has no 'nets' section: {path}")

    components: dict[str, Component] = {}
    for comp in _sexp_get_all(components_section, "comp"):
        ref = _sexp_get_val(comp, "ref")
        if ref is None:
            raise GateError(f"netlist has a 'comp' entry with no 'ref': {comp!r}")
        footprint = _sexp_get_val(comp, "footprint") or ""
        sheetpath = _sexp_get(comp, "sheetpath")
        names = _sexp_get_val(sheetpath, "names") if sheetpath else None
        instance_path = ""
        if names:
            # names looks like ".../main.ato:Top::safety.fault_or" (or, for
            # the root sheet, may have no "::" at all).
            instance_path = names.rsplit("::", 1)[-1] if "::" in names else ""
        components[ref] = Component(ref=ref, footprint=footprint, instance_path=instance_path)

    nets: dict[str, Net] = {}
    pin_to_net: dict[tuple, str] = {}
    net_entries = _sexp_get_all(nets_section, "net")
    if not net_entries:
        raise GateError(f"netlist 'nets' section has zero net entries: {path}")

    for net_node in net_entries:
        code = _sexp_get_val(net_node, "code")
        name = _sexp_get_val(net_node, "name") or ""
        if code is None:
            raise GateError(f"netlist has a 'net' entry with no 'code': {net_node!r}")
        nodes = []
        for node in _sexp_get_all(net_node, "node"):
            ref = _sexp_get_val(node, "ref")
            pin = _sexp_get_val(node, "pin")
            if ref is None or pin is None:
                raise GateError(f"netlist has a malformed 'node' entry: {node!r}")
            nodes.append((ref, pin))
            pin_to_net[(ref, pin)] = code
        nets[code] = Net(code=code, name=name, nodes=nodes)

    return Netlist(components=components, nets=nets, pin_to_net=pin_to_net)


def load_identity(path: Path) -> dict:
    """Return {ref: mpn} from elec/build/default.csv.

    default.csv groups components by their real `mpn` attribute (set
    directly in elec/src/components.ato), not by footprint -- this is the
    identity source of truth per the netlist caveat above. The "LCSC"
    column is populated from `components.get_mpn()` in atopile's BOM
    generator; "Comment" is a user-facing value field that happens to
    equal the MPN for parts with no separate `value` trait (true for every
    IC in this design) and is used only as a consistency cross-check.
    """
    if not path.is_file():
        raise GateError(f"BOM not found: {path}")
    text = path.read_text()
    if not text.strip():
        raise GateError(f"BOM is empty: {path}")

    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames is None or "Designator" not in reader.fieldnames:
        raise GateError(
            f"BOM has no 'Designator' column (got {reader.fieldnames!r}): {path}"
        )
    if "LCSC" not in reader.fieldnames:
        raise GateError(f"BOM has no 'LCSC' column (got {reader.fieldnames!r}): {path}")

    ref_to_mpn: dict[str, str] = {}
    row_count = 0
    for row in reader:
        row_count += 1
        designators = [d.strip() for d in (row.get("Designator") or "").split(",") if d.strip()]
        mpn = (row.get("LCSC") or "").strip()
        if not designators or not mpn:
            continue
        for ref in designators:
            ref_to_mpn[ref] = mpn

    if row_count == 0:
        raise GateError(f"BOM has a header but zero data rows: {path}")
    if not ref_to_mpn:
        raise GateError(f"BOM parsed {row_count} rows but produced zero (ref -> mpn) entries: {path}")

    return ref_to_mpn


def load_registry(path: Path) -> dict:
    if not path.is_file():
        raise GateError(f"package registry config not found: {path}")
    with open(path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "packages" not in data or "fault_tree" not in data:
        raise GateError(
            f"package registry config missing required top-level keys "
            f"'packages'/'fault_tree': {path}"
        )
    if not data.get("required_packages"):
        raise GateError(f"package registry config has no 'required_packages': {path}")
    return data


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------

OCCUPIED = "OCCUPIED"
GND_TIED = "GND_TIED"
UNREFERENCED = "UNREFERENCED"

AVAILABLE = "AVAILABLE"
UNUSABLE = "UNUSABLE"


@dataclass
class GateInputResult:
    ref: str
    instance_path: str
    gate_name: str
    pin_name: str
    net_code: str | None
    occupancy: str  # OCCUPIED / GND_TIED / UNREFERENCED
    occupant_desc: str
    verdict: str  # AVAILABLE / UNUSABLE
    reason: str


@dataclass
class PackageInstance:
    ref: str
    mpn: str
    instance_path: str


def find_instances(netlist: Netlist, ref_to_mpn: dict, mpn: str) -> list[PackageInstance]:
    out = []
    for ref, comp in netlist.components.items():
        if ref_to_mpn.get(ref) == mpn:
            out.append(PackageInstance(ref=ref, mpn=mpn, instance_path=comp.instance_path))
    return sorted(out, key=lambda p: p.ref)


def _own_gnd_net(netlist: Netlist, pkg_def: dict, ref: str) -> str | None:
    gnd_pin = pkg_def["pins"].get("GND")
    if gnd_pin is None:
        return None
    return netlist.net_of(ref, gnd_pin)


def _describe_pin(netlist: Netlist, ref_to_mpn: dict, ref: str, pin: str) -> str:
    comp = netlist.components.get(ref)
    path = comp.instance_path if comp and comp.instance_path else ref
    mpn = ref_to_mpn.get(ref, "?")
    return f"{path} (ref {ref}, {mpn}, pin {pin})"


def classify_occupancy(
    netlist: Netlist,
    ref_to_mpn: dict,
    ref: str,
    pin: str,
    own_gnd_net: str | None,
) -> tuple:
    """Return (occupancy, occupant_desc, net_code)."""
    net_code = netlist.net_of(ref, pin)
    if net_code is None:
        return UNREFERENCED, "no net entry at all (pin absent from netlist)", None

    net = netlist.nets[net_code]
    others = [(r, p) for (r, p) in net.nodes if not (r == ref and p == pin)]

    if own_gnd_net is not None and net_code == own_gnd_net:
        return GND_TIED, "tied to this package's own GND (shared board return)", net_code

    if not others:
        return UNREFERENCED, "singleton net -- not wired to anything", net_code

    desc = ", ".join(_describe_pin(netlist, ref_to_mpn, r, p) for r, p in others)
    return OCCUPIED, desc, net_code


def build_gate_edges(
    netlist: Netlist,
    ref_to_mpn: dict,
    registry: dict,
    aggregator_mpns: list,
) -> dict:
    """Build {net_code: set(net_code)} forward edges: an input pin's net
    points at its gate's output pin's net, for every instantiated
    aggregator package. This models "if a signal appears on this input,
    it appears on the gate's output" -- true for any OR-type fan-in gate
    regardless of the other inputs' state.
    """
    edges: dict[str, set] = {}
    for mpn in aggregator_mpns:
        pkg_def = registry["packages"].get(mpn)
        if pkg_def is None:
            raise GateError(
                f"fault_tree.aggregator_mpns references unrecognised package "
                f"'{mpn}' -- add it to the 'packages' section of the config."
            )
        for inst in find_instances(netlist, ref_to_mpn, mpn):
            for gate in pkg_def.get("gates", []):
                out_pin = pkg_def["pins"].get(gate["output"])
                if out_pin is None:
                    raise GateError(
                        f"package '{mpn}' gate '{gate['name']}' output "
                        f"'{gate['output']}' is not in its pin map"
                    )
                out_net = netlist.net_of(inst.ref, out_pin)
                if out_net is None:
                    continue  # output pin literally absent from netlist
                for in_name in gate["inputs"]:
                    in_pin = pkg_def["pins"].get(in_name)
                    if in_pin is None:
                        raise GateError(
                            f"package '{mpn}' gate '{gate['name']}' input "
                            f"'{in_name}' is not in its pin map"
                        )
                    in_net = netlist.net_of(inst.ref, in_pin)
                    if in_net is None:
                        continue
                    edges.setdefault(in_net, set()).add(out_net)
    return edges


def reachable_nets(start_net: str, edges: dict) -> set:
    seen = {start_net}
    frontier = [start_net]
    while frontier:
        current = frontier.pop()
        for nxt in edges.get(current, ()):
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    return seen


@dataclass
class PackageReport:
    ref: str
    mpn: str
    instance_path: str
    gates: list  # list[GateInputResult] flattened


@dataclass
class CapacityReport:
    packages: list  # list[PackageReport]
    total_inputs: int
    total_available: int
    total_unusable: int
    total_occupied: int
    defects: list  # list[str] human-readable defect descriptions
    nets_inspected: int
    pins_inspected: int


def analyze(netlist: Netlist, ref_to_mpn: dict, registry: dict) -> CapacityReport:
    ft = registry["fault_tree"]
    aggregator_mpns = ft["aggregator_mpns"]
    dest_mpn = ft["destination_mpn"]
    set_pin_name = ft["set_pin"]
    reset_pin_name = ft.get("reset_qualifier_pin")
    reset_reason = ft.get("reset_qualifier_reason", "reaches only the reset-qualifier path")

    dest_pkg_def = registry["packages"].get(dest_mpn)
    if dest_pkg_def is None:
        raise GateError(f"fault_tree.destination_mpn '{dest_mpn}' is not in 'packages'")

    dest_instances = find_instances(netlist, ref_to_mpn, dest_mpn)
    if len(dest_instances) != 1:
        raise GateError(
            f"fault_tree.destination_mpn '{dest_mpn}' must have exactly one "
            f"instance in the design; found {len(dest_instances)} "
            f"({[i.ref for i in dest_instances]}). Destination is ambiguous."
        )
    dest = dest_instances[0]
    set_pin = dest_pkg_def["pins"].get(set_pin_name)
    if set_pin is None:
        raise GateError(f"destination package pin map has no '{set_pin_name}' (set_pin)")
    set_net = netlist.net_of(dest.ref, set_pin)
    if set_net is None:
        raise GateError(
            f"destination SET pin {dest.ref}.{set_pin_name} has no net in the "
            f"netlist at all -- cannot evaluate reachability"
        )

    reset_net = None
    if reset_pin_name:
        reset_pin = dest_pkg_def["pins"].get(reset_pin_name)
        if reset_pin is not None:
            reset_net = netlist.net_of(dest.ref, reset_pin)

    edges = build_gate_edges(netlist, ref_to_mpn, registry, aggregator_mpns)

    package_reports = []
    total_inputs = 0
    total_available = 0
    total_unusable = 0
    total_occupied = 0
    defects = []
    pins_inspected = set()

    for mpn in aggregator_mpns:
        pkg_def = registry["packages"][mpn]
        for inst in find_instances(netlist, ref_to_mpn, mpn):
            own_gnd_net = _own_gnd_net(netlist, pkg_def, inst.ref)
            gate_results = []
            for gate in pkg_def["gates"]:
                out_pin = pkg_def["pins"][gate["output"]]
                out_net = netlist.net_of(inst.ref, out_pin)
                pins_inspected.add((inst.ref, out_pin))
                gate_has_real_occupant = False
                gate_output_reaches_anything = False
                if out_net is not None:
                    out_others = [
                        (r, p)
                        for (r, p) in netlist.nets[out_net].nodes
                        if not (r == inst.ref and p == out_pin)
                    ]
                    gate_output_reaches_anything = len(out_others) > 0
                reached = reachable_nets(out_net, edges) if out_net is not None else set()
                reaches_set = set_net in reached
                reaches_reset_only = (
                    reset_net is not None and reset_net in reached and not reaches_set
                )

                for in_name in gate["inputs"]:
                    in_pin = pkg_def["pins"][in_name]
                    pins_inspected.add((inst.ref, in_pin))
                    total_inputs += 1
                    occupancy, occupant_desc, net_code = classify_occupancy(
                        netlist, ref_to_mpn, inst.ref, in_pin, own_gnd_net
                    )

                    is_cascade = False
                    if occupancy == OCCUPIED and net_code is not None:
                        # A cascade input is one whose occupant is another
                        # aggregator gate's output pin (or the pin's own
                        # gate output pin looped back), not an external
                        # fault source.
                        for r, p in netlist.nets[net_code].nodes:
                            if r == inst.ref and p == in_pin:
                                continue
                            for other_mpn in aggregator_mpns:
                                other_def = registry["packages"].get(other_mpn)
                                if not other_def:
                                    continue
                                if ref_to_mpn.get(r) == other_mpn:
                                    out_pins = {
                                        other_def["pins"][g["output"]]
                                        for g in other_def["gates"]
                                    }
                                    if p in out_pins:
                                        is_cascade = True

                    if occupancy == OCCUPIED and not is_cascade:
                        gate_has_real_occupant = True
                        total_occupied += 1
                        verdict, reason = UNUSABLE, f"occupied by {occupant_desc}"
                    elif occupancy == OCCUPIED and is_cascade:
                        total_occupied += 1
                        verdict, reason = UNUSABLE, f"occupied by internal cascade: {occupant_desc}"
                    else:
                        # GND_TIED or UNREFERENCED: a candidate spare input.
                        if not gate_output_reaches_anything:
                            verdict, reason = (
                                UNUSABLE,
                                f"gate '{gate['name']}' output {gate['output']} "
                                f"drives nothing (dead gate) -- {occupancy.lower()}",
                            )
                        elif reaches_reset_only:
                            verdict, reason = (
                                UNUSABLE,
                                f"gate '{gate['name']}' output reaches only the "
                                f"reset-qualifier pin ({dest.ref}.{reset_pin_name}): "
                                f"{reset_reason}",
                            )
                        elif reaches_set:
                            verdict, reason = (
                                AVAILABLE,
                                f"{occupancy.lower()}; gate '{gate['name']}' output "
                                f"reaches SET pin {dest.ref}.{set_pin_name}",
                            )
                        else:
                            verdict, reason = (
                                UNUSABLE,
                                f"gate '{gate['name']}' output does not reach the "
                                f"SET pin {dest.ref}.{set_pin_name}",
                            )

                    if verdict == AVAILABLE:
                        total_available += 1
                    else:
                        total_unusable += 1

                    gate_results.append(
                        GateInputResult(
                            ref=inst.ref,
                            instance_path=inst.instance_path,
                            gate_name=gate["name"],
                            pin_name=in_name,
                            net_code=net_code,
                            occupancy=occupancy,
                            occupant_desc=occupant_desc,
                            verdict=verdict,
                            reason=reason,
                        )
                    )

                if gate_has_real_occupant and not gate_output_reaches_anything:
                    defects.append(
                        f"{inst.instance_path or inst.ref}.{gate['name']} "
                        f"(ref {inst.ref}): has a real signal wired into an input "
                        f"but its output {gate['output']} drives nothing -- a "
                        f"fault source wired here is a silent no-op"
                    )

            package_reports.append(
                PackageReport(
                    ref=inst.ref,
                    mpn=mpn,
                    instance_path=inst.instance_path,
                    gates=gate_results,
                )
            )

    return CapacityReport(
        packages=package_reports,
        total_inputs=total_inputs,
        total_available=total_available,
        total_unusable=total_unusable,
        total_occupied=total_occupied,
        defects=defects,
        nets_inspected=len(netlist.nets),
        pins_inspected=len(pins_inspected),
    )


def check_required_packages(netlist: Netlist, ref_to_mpn: dict, registry: dict) -> None:
    present_mpns = set(ref_to_mpn.get(ref) for ref in netlist.components)
    for required in registry["required_packages"]:
        matches = [ref for ref, mpn in ref_to_mpn.items() if mpn == required and ref in netlist.components]
        if not matches:
            raise GateError(
                f"required package '{required}' has zero instances in the "
                f"design -- this is far more likely a build/parsing "
                f"regression than a real design change (anti-vacuity gate)"
            )
    if not present_mpns:
        raise GateError("BOM identity mapping produced zero recognised packages")


def format_report(report: CapacityReport, registry: dict) -> str:
    lines = []
    ft = registry["fault_tree"]
    lines.append("=== DESIGN CAPACITY BUDGET: fault-tree logic-gate fan-in ===")
    lines.append(
        f"Packages inspected: {len(report.packages)} | "
        f"nets inspected: {report.nets_inspected} | "
        f"pins inspected: {report.pins_inspected} | "
        f"SET-path inputs evaluated: {report.total_inputs}"
    )
    lines.append(
        f"AVAILABLE: {report.total_available}  |  "
        f"UNUSABLE: {report.total_unusable}  |  OCCUPIED: {report.total_occupied}"
    )
    lines.append("")
    for pkg in report.packages:
        lines.append(f"--- {pkg.instance_path or pkg.ref} (ref {pkg.ref}, {pkg.mpn}) ---")
        by_gate: dict = {}
        for g in pkg.gates:
            by_gate.setdefault(g.gate_name, []).append(g)
        for gate_name, results in by_gate.items():
            lines.append(f"  {gate_name}:")
            for r in results:
                lines.append(
                    f"    {r.pin_name:>3} [{r.occupancy:12}] -> {r.verdict:10} :: {r.reason}"
                )
    if report.defects:
        lines.append("")
        lines.append("=== CAPACITY DEFECTS (blocking) ===")
        for d in report.defects:
            lines.append(f"  FAIL: {d}")
    lines.append("")
    lines.append(
        f"SET pin: {ft['destination_mpn']}.{ft['set_pin']}  |  "
        f"reset-qualifier pin: {ft['destination_mpn']}.{ft.get('reset_qualifier_pin')}"
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--netlist", type=Path, default=DEFAULT_NETLIST)
    parser.add_argument("--bom", type=Path, default=DEFAULT_BOM)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()

    try:
        registry = load_registry(args.config)
        netlist = load_netlist(args.netlist)
        ref_to_mpn = load_identity(args.bom)
        check_required_packages(netlist, ref_to_mpn, registry)
        report = analyze(netlist, ref_to_mpn, registry)
    except GateError as e:
        print("=== DESIGN CAPACITY BUDGET GATE: TOOL ERROR ===", file=sys.stderr)
        print(
            "GATE RESULT: ERROR — not PASSED, not a capacity defect. "
            "The check did not complete a normal run.",
            file=sys.stderr,
        )
        print(f"Reason: {e}", file=sys.stderr)
        gh_summary_path = get_github_summary_path()
        if gh_summary_path:
            with open(gh_summary_path, "a") as gh:
                gh.write("### Design Capacity Budget Gate — TOOL ERROR\n")
                gh.write(f"Reason: {e}\n")
        sys.exit(5)

    text = format_report(report, registry)
    print(text)

    gh_summary_path = get_github_summary_path()
    if gh_summary_path:
        with open(gh_summary_path, "a") as gh:
            gh.write("### Design Capacity Budget Gate\n")
            gh.write("```\n" + text + "\n```\n")

    if report.total_available == 0:
        print(
            "\nWARNING: 0 genuinely available SET-path inputs across all "
            "tracked aggregator packages. This is a legitimate design "
            "state (see docs/hardware/UVL02_DESIGN.md SS7.1) that requires "
            "a human decision (rework the tree or add a package), not a "
            "gate failure.",
        )

    if report.defects:
        print(f"\nDesign capacity budget gate FAILED: {len(report.defects)} defect(s)")
        sys.exit(3)

    print("\nDesign capacity budget gate PASSED — 0 defects")
    sys.exit(0)


if __name__ == "__main__":
    main()
