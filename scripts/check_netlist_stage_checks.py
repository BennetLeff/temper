#!/usr/bin/env python3
"""Netlist-stage checks gate (docs/STRATEGY.md build order step 6).

STRATEGY.md's "Checks by stage" table names five checks that should run at
the netlist stage, "safety-critical, milliseconds, currently absent; the
most validatable loop we have": isolation-domain reachability,
voltage-domain compatibility, single-pin nets, unconnected power pins, and
part stress vs. abs-max.

Isolation-domain reachability with isolators as cut vertices ALREADY EXISTS
and is ALREADY CI-wired: ``scripts/check_domain_partition.py`` (added
2026-07-31, commit ``ee3da42a``) computes connected components of exactly
this graph and fails on any HV<->SELV crossing or isolator-barrier breach --
it is the check that would have caught, and on 2026-07-26 evidence records
that it DID catch, the star-point join short this project's own history
names. Re-implementing it here would duplicate 900+ lines of already-tested
graph machinery for no safety benefit; this gate imports and reuses its
netlist parser, freshness check, and domain-manifest loader instead of
re-deriving them, and its GateError/exit-code contract, matching the
convention ``check_netlist_board_reconciliation.py`` already set for
"import the canonical gate's primitives rather than re-deriving them".

This gate implements the remaining three of "at minimum" and-currently-
genuinely-absent netlist-stage checks:

  1. SINGLE-PIN NETS -- a compiled net with exactly one (ref, pin) node.
     Almost always a wiring error (the far end was never connected).

  2. UNCONNECTED POWER PINS -- a component's declared power/ground pin
     (identified from its ``component`` class definition in
     ``elec/src/components.ato``, never from net-name substring matching --
     see "Why pin identity, not net-name substrings" below) that either
     never appears in the compiled netlist at all, or appears on a net with
     no other connection (net_nodes length <= 1, i.e. a pin wired only to
     itself). This overlaps single-pin nets by construction whenever the
     culprit net has exactly one node; that is intentional, not a bug --
     see "Relationship to the single-pin-nets check" below.

  3. VOLTAGE-DOMAIN COMPATIBILITY -- a net belonging to a domain declared in
     a specific, EXPLICITLY-VOLTAGE-NAMED net (e.g. "+170V_BUS", "+15V",
     "+15V_LS", "+3V3" -- there are 4 in this design) must not connect a
     component whose OWN declared ``voltage_rating`` (from
     ``elec/src/*.ato``, the source of truth for that value -- it is never
     present in the compiled netlist or in ``elec/build/default.csv``) is
     below that SPECIFIC net's own named magnitude (e.g. "+170V_BUS" gives a
     floor of 170V, checked ONLY against components with a pin literally on
     that net; never against every other net in the same HV domain). This is
     deliberately narrower than "every net in the domain": an earlier
     version of this check propagated a domain-wide floor (the domain's own
     max explicit voltage) onto every net in that domain, and flagged
     ordinary 10V-rated 0603 decoupling capacitors on "gnd" as violations
     against a 170V HV-domain ceiling -- "gnd" is reachable from an
     HV-domain net elsewhere in the design (by isolation-topology
     membership) but carries ~0V itself, and a domain-wide floor cannot see
     that difference. Scoping to the net's own explicit name is also a
     deliberate echo of docs/STRATEGY.md's own "default.net aliases part
     identity by footprint" section, which documents this same project
     getting a "+340V_BUS" net name wrong for what turned out to be a 170V
     half-bus node -- deriving the floor from a NET'S own name (never from a
     domain's informal English label "HV") avoids repeating that mistake.
     See ``compute_net_voltage_floors()`` below for the full false-positive
     writeup.

"Part stress vs. abs-max" (the fifth item in STRATEGY.md's table) is
explicitly out of scope: it needs abs-max ratings this design does not
currently record in machine-readable form anywhere (SOA/derating curves,
not a single voltage_rating scalar), and inventing a stand-in would be
exactly the kind of unsourced-number gate this project's own history
(docs/STRATEGY.md, "The 390-410V spec has no derivation") warns against.

Why pin identity comes from elec/src/*.ato, never elec/build/default.net
--------------------------------------------------------------------------
docs/STRATEGY.md's "default.net aliases part identity by footprint" section
(2026-07-26) documents that atopile's netlist exporter collapses the
``libsource``/``libparts`` identity of every component sharing a KiCad
footprint -- ten distinct SOT-23-5 parts (REF2025, six TLV3201 instances,
SN74LVC1G08, SN74LVC1G38, TPS3823) all present as "REF2025AIDDCR" in
``default.net``. That same document confirms the ``(nets ...)`` section
itself keys on ``(ref, pin)``, not ``libsource``, so which NET a pin is on
is trustworthy -- but which COMPONENT CLASS (and therefore which pins are
power/ground, and what voltage_rating applies) a given ref actually is, is
NOT trustworthy from ``.net``'s own identity fields. This gate resolves that
the same way ``elec/domain_manifest.yaml``'s isolator entries do: by
instance path (the ``sheetpath`` "names" field, stable and NOT footprint-
aliased) matched against a class model built directly from
``elec/src/*.ato`` -- the same source ``ato build`` itself compiles. See
``resolve_instances()``/``parse_ato_classes()`` below.

Fail-closed contract (METHODOLOGY.md Sec 4/5), matching
check_domain_partition.py / check_netlist_board_reconciliation.py: never
exits 0 unless it positively confirms it ran a real check on real, fresh
data. Exits non-zero -- never silently 0 -- for every one of:
  - the netlist file is missing, empty, or STALE (delegates to
    check_domain_partition.check_netlist_freshness)
  - the domain manifest is missing, empty, malformed, or names a net not
    present in the compiled netlist (delegates to
    check_domain_partition.load_manifest / the same net-existence check
    check_domain_partition itself performs)
  - a declared domain has no net whose name carries an explicit voltage
    magnitude (the floor-derivation precondition above)
  - the allowlist file is present but malformed
  - elec/src/*.ato cannot be parsed into a non-empty class model, or the
    "Top" root class does not exist

Exit codes:
  0 - PASSED: 0 non-allowlisted findings across all three checks
  3 - VIOLATION: at least one non-allowlisted finding
  5 - GATE ERROR: the gate could not run a trustworthy check at all

Usage:
  uv run python scripts/check_netlist_stage_checks.py
  uv run python scripts/check_netlist_stage_checks.py --netlist PATH --manifest PATH
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402
from check_domain_partition import (  # noqa: E402
    GateError,
    Netlist,
    build_name_to_code,
    check_netlist_freshness,
    parse_netlist,
)
from check_domain_partition import (
    Manifest as DomainManifest,
)
from check_domain_partition import (
    load_manifest as load_domain_manifest,
)

REPO_ROOT = find_repo_root()
DEFAULT_NETLIST = REPO_ROOT / "elec" / "build" / "default.net"
DEFAULT_DOMAIN_MANIFEST = REPO_ROOT / "elec" / "domain_manifest.yaml"
DEFAULT_SRC_DIR = REPO_ROOT / "elec" / "src"
DEFAULT_ALLOWLIST = REPO_ROOT / "netlist-stage-checks-allowlist.yaml"

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

ATO_SOURCE_FILES = [
    "components.ato",
    "modules.ato",
    "main.ato",
    "constraints.ato",
    "interfaces.ato",
    "footprints.ato",
    "fac_utils.ato",
]


# ---------------------------------------------------------------------------
# elec/src/*.ato class model
#
# atopile's own grammar has no loops or conditionals in this design (verified
# directly: zero top-level `for`/`if` statements across elec/src/*.ato), and
# every `component`/`module`/`interface` header in this design is anchored at
# column 0 with no nesting of class DEFINITIONS inside other class
# definitions (only INSTANCES nest). That lets a flat, indentation-aware
# line scan build an accurate model without needing a real atopile parser.
# ---------------------------------------------------------------------------


@dataclass
class AtoClass:
    name: str
    kind: str  # "component" | "module" | "interface"
    instances: dict[str, str] = field(default_factory=dict)  # local_name -> class_name
    voltage_sets: dict[str, float] = field(default_factory=dict)  # local_name -> volts
    own_default_voltage: float | None = None  # bare `voltage_rating = X` inside a component class
    pins: dict[str, str] = field(default_factory=dict)  # pin_number -> signal_name (component classes only)


_CLASS_HEADER_RE = re.compile(r"^(component|module|interface)\s+(\w+)\s*:")
_NEW_RE = re.compile(r"^(\w+)\s*=\s*new\s+(\w+)\b")
_ATTR_VOLTAGE_RE = re.compile(r"^(\w+)\.voltage_rating\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]*)")
_BARE_VOLTAGE_RE = re.compile(r"^voltage_rating\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]*)")
_SIGNAL_PIN_RE = re.compile(r"^signal\s+(\w+)\s*~\s*pin\s+(\d+)\b")

_VOLTAGE_UNITS = {"": 1.0, "V": 1.0, "kV": 1000.0, "mV": 0.001}


def _to_volts(num: str, unit: str) -> float:
    unit = unit.strip()
    if unit not in _VOLTAGE_UNITS:
        raise GateError(
            f"unrecognized voltage unit {unit!r} parsing {num}{unit} in "
            "elec/src/*.ato -- fail closed rather than silently mis-scale a "
            "safety-relevant rating"
        )
    return float(num) * _VOLTAGE_UNITS[unit]


def parse_ato_classes(paths: list[Path]) -> dict[str, AtoClass]:
    """Build a class model (instances, voltage_rating assignments, physical
    pin map) from elec/src/*.ato, skipping comments and docstrings."""
    classes: dict[str, AtoClass] = {}
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        current: AtoClass | None = None
        in_docstring = False
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue

            quote_count = stripped.count('"""')
            if in_docstring:
                if quote_count % 2 == 1:
                    in_docstring = False
                continue
            if quote_count == 1:
                in_docstring = True
                continue
            if quote_count >= 2:
                continue  # single-line docstring; its content is prose, never code

            indent = len(raw_line) - len(raw_line.lstrip())
            m = _CLASS_HEADER_RE.match(stripped)
            if m:
                kind, name = m.groups()
                current = classes.setdefault(name, AtoClass(name=name, kind=kind))
                continue
            if indent == 0:
                # Dedent to column 0 without being a class header: a
                # top-level instantiation (e.g. `temper = new Top`), an
                # import, or a file-header comment. Close the active class
                # so this line is never misattributed as one of ITS
                # members -- misattributing `temper = new Top` into Top's
                # own instance dict would make Top instantiate itself and
                # send resolve_instances() into infinite recursion.
                current = None
                continue
            if current is None:
                continue
            m = _NEW_RE.match(stripped)
            if m:
                local, sub_class = m.groups()
                current.instances[local] = sub_class
                continue
            m = _ATTR_VOLTAGE_RE.match(stripped)
            if m:
                local, num, unit = m.groups()
                current.voltage_sets[local] = _to_volts(num, unit)
                continue
            m = _BARE_VOLTAGE_RE.match(stripped)
            if m:
                num, unit = m.groups()
                current.own_default_voltage = _to_volts(num, unit)
                continue
            m = _SIGNAL_PIN_RE.match(stripped)
            if m:
                sig, pin = m.groups()
                current.pins[pin] = sig
                continue
    return classes


@dataclass
class ResolvedInstance:
    path: str
    class_name: str
    voltage_rating: float | None


def resolve_instances(classes: dict[str, AtoClass], root: str = "Top") -> dict[str, ResolvedInstance]:
    """Walk the class model from `root` (the atopile build entry's root
    class, matching elec/ato.yaml's `builds.default.entry: src/main.ato:Top`)
    and assign every instance the SAME dotted path scheme the compiled
    netlist's sheetpath uses (e.g. "hb.power_loop.q_high"), together with
    its resolved voltage_rating: a per-instance override
    (`name.voltage_rating = X` set where the instance is declared) if
    present, else the instantiated class's own baked-in default (a bare
    `voltage_rating = X` inside a fixed-part `component` definition like
    IKW40N120H3), else None (no rating known -- never guessed)."""
    if root not in classes:
        raise GateError(
            f"root class {root!r} not found in elec/src/*.ato class model -- "
            "parsing failed or the build entry point changed"
        )
    result: dict[str, ResolvedInstance] = {}

    def walk(class_name: str, prefix: str, seen: frozenset[str]) -> None:
        node = classes.get(class_name)
        if node is None:
            return
        if class_name in seen:
            raise GateError(
                f"instantiation cycle detected in elec/src/*.ato: {class_name!r} "
                f"instantiates itself (directly or transitively) under {prefix!r}"
            )
        seen = seen | {class_name}
        for local_name, sub_class in node.instances.items():
            full_path = f"{prefix}.{local_name}" if prefix else local_name
            voltage = node.voltage_sets.get(local_name)
            if voltage is None:
                sub_node = classes.get(sub_class)
                if sub_node is not None:
                    voltage = sub_node.own_default_voltage
            result[full_path] = ResolvedInstance(path=full_path, class_name=sub_class, voltage_rating=voltage)
            walk(sub_class, full_path, seen)

    walk(root, "", frozenset())
    if not result:
        raise GateError(
            f"root class {root!r} resolved zero instances -- elec/src/*.ato "
            "parsing produced an empty design (should be impossible on a "
            "real design; treat as a parser bug, not '0 findings')"
        )
    return result


# Whole-token match against a component's OWN declared pin name (never a net
# name -- see module docstring's "Why pin identity" section for why net-name
# substring matching is the specific, three-times-repeated bug class this
# project's own docs/STRATEGY.md documents and this check deliberately
# avoids). Anchored full-string match, not `in`: "VBIAS"/"VREF"/"VO" (real
# pin names in this design's own components.ato) do not match despite
# starting with "V", because they are not literally "V" + CC/DD/SS/IN/P/N/S.
POWER_PIN_RE = re.compile(r"^(V(CC|DD|SS)\w*|V(IN|P|N|S)|GND\w*|DGND)$")


def is_power_pin_name(signal_name: str) -> bool:
    return bool(POWER_PIN_RE.match(signal_name))


@dataclass
class PowerPin:
    instance_path: str
    pin_number: str
    signal_name: str


def find_power_pins(classes: dict[str, AtoClass], resolved: dict[str, ResolvedInstance]) -> list[PowerPin]:
    out: list[PowerPin] = []
    for path, inst in resolved.items():
        cls = classes.get(inst.class_name)
        if cls is None or cls.kind != "component" or not cls.pins:
            continue
        for pin_num, sig in cls.pins.items():
            if is_power_pin_name(sig):
                out.append(PowerPin(instance_path=path, pin_number=pin_num, signal_name=sig))
    return sorted(out, key=lambda p: (p.instance_path, p.pin_number))


def path_to_ref(netlist: Netlist) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for ref, comp in netlist.components.items():
        if comp.instance_path:
            mapping[comp.instance_path] = ref
    return mapping


# ---------------------------------------------------------------------------
# Check 1: single-pin nets
# ---------------------------------------------------------------------------


@dataclass
class SinglePinNetFinding:
    net_name: str
    ref: str
    pin: str


def check_single_pin_nets(netlist: Netlist) -> list[SinglePinNetFinding]:
    findings = []
    for code, nodes in netlist.net_nodes.items():
        if len(nodes) == 1:
            ref, pin = nodes[0]
            findings.append(SinglePinNetFinding(net_name=netlist.nets[code], ref=ref, pin=pin))
    return sorted(findings, key=lambda f: (f.net_name, f.ref, f.pin))


# ---------------------------------------------------------------------------
# Check 2: unconnected power pins
#
# Relationship to the single-pin-nets check: a power pin whose net has
# exactly one node is found by BOTH checks. That is intentional, not
# duplicate coverage to be suppressed -- check 1 is a generic connectivity
# sweep over every net; check 2 specifically walks every component's
# DECLARED power/ground pins (resolved from elec/src/components.ato, not
# net names) and flags the safety-relevant subset. A future net-name change
# that accidentally moves a power pin onto a *shared, multi-node* signal net
# would be invisible to check 1 (that net legitimately has >1 node) but is
# exactly the shape of defect this check is scoped to catch WITHOUT also
# claiming coverage this gate cannot yet deliver: distinguishing "shared
# with other power pins" from "shared with an ordinary passive's generic p1/
# p2 terminal" was tried and rejected -- ordinary decoupling capacitors sit
# on VCC/GND nets via generically-named p1/p2 pins that are not themselves
# power-pin-named, so "does this net carry >=1 OTHER declared power pin"
# would false-positive on every ordinary bypass-cap net in the design. The
# scope actually implemented -- "never wired at all" or "wired to a net
# nothing else touches" -- has zero such false-positive exposure.
# ---------------------------------------------------------------------------


@dataclass
class UnconnectedPowerPinFinding:
    instance_path: str
    ref: str
    pin: str
    signal_name: str
    reason: str


def check_unconnected_power_pins(
    netlist: Netlist, power_pins: list[PowerPin], ref_of_path: dict[str, str]
) -> list[UnconnectedPowerPinFinding]:
    findings = []
    for pp in power_pins:
        ref = ref_of_path.get(pp.instance_path)
        if ref is None:
            continue  # this instance is not present in the compiled netlist at all
        net_code = netlist.pin_net.get((ref, pp.pin_number))
        if net_code is None:
            findings.append(
                UnconnectedPowerPinFinding(
                    pp.instance_path, ref, pp.pin_number, pp.signal_name,
                    "power/ground pin absent from the compiled netlist entirely",
                )
            )
            continue
        nodes = netlist.net_nodes.get(net_code, [])
        if len(nodes) <= 1:
            findings.append(
                UnconnectedPowerPinFinding(
                    pp.instance_path, ref, pp.pin_number, pp.signal_name,
                    f"net {netlist.nets[net_code]!r} has no other connection -- "
                    "power/ground pin is floating",
                )
            )
    return sorted(findings, key=lambda f: (f.instance_path, f.pin))


# ---------------------------------------------------------------------------
# Check 3: voltage-domain compatibility
# ---------------------------------------------------------------------------

_NET_VOLTAGE_RE = re.compile(r"(\d+)V(\d*)")


def _explicit_net_voltage(name: str) -> float | None:
    """Extract an explicit voltage magnitude from a net's own name, e.g.
    "+170V_BUS" -> 170.0, "+15V_LS" -> 15.0, "+3V3" -> 3.3 (the "V-as-decimal-
    point" convention this design's own net names already use). Returns None
    for names with no such pattern -- never a guess."""
    m = _NET_VOLTAGE_RE.search(name)
    if not m:
        return None
    whole, frac = m.groups()
    return float(f"{whole}.{frac}") if frac else float(whole)


def compute_net_voltage_floors(manifest: DomainManifest) -> dict[str, tuple[str, float]]:
    """Map net_name -> (domain, explicit_voltage) for every net, across every
    declared domain, whose OWN name carries an explicit voltage magnitude
    (e.g. "+170V_BUS" -> ("HV", 170.0)).

    Deliberately scoped to the NAMED net itself, not propagated across every
    other net in the same domain. An earlier version of this check used one
    floor per DOMAIN (the max explicit voltage found anywhere in that
    domain's net list) and applied it to every net in the domain -- which
    flagged, among other things, ordinary 10V-rated 0603 decoupling
    capacitors sitting between "+3V3" and "gnd" as violations against a
    170V HV-domain ceiling, because "gnd" is also reachable from an
    HV-domain net elsewhere in the design. "gnd" itself carries ~0V under
    normal operation; a domain-wide floor cannot see that; only the net's
    OWN name can. This is exactly the false-positive failure mode this
    project's own history already burned a fix on (docs/STRATEGY.md,
    creepage_check.py: "L1"/"L2"/"LINE" substring matches produced 24 false
    positives on SELV nets) -- inferring an electrical property from
    domain-membership-by-association rather than from the net's own
    declared identity. Scoping to explicitly-named nets keeps every floor
    traceable to a real, specific voltage instead of an inferred one, at
    the cost of only checking the ~4 nets in this design that name a
    voltage at all -- a smaller but zero-false-positive-by-construction
    check, matching this gate's fail-closed contract better than a broader
    but unreliable one."""
    floors: dict[str, tuple[str, float]] = {}
    for domain, nets in manifest.domains.items():
        for net_name in nets:
            voltage = _explicit_net_voltage(net_name)
            if voltage is not None:
                floors[net_name] = (domain, voltage)
    if not floors:
        raise GateError(
            "no net across any declared domain (elec/domain_manifest.yaml) "
            "carries an explicit voltage in its own name (e.g. '+15V', "
            "'+170V_BUS') -- cannot check voltage-domain compatibility "
            "without a real, named floor; refusing to invent one"
        )
    return floors


@dataclass
class VoltageDomainFinding:
    domain: str
    floor_voltage: float
    net_name: str
    instance_path: str
    ref: str
    voltage_rating: float


def check_voltage_domain_compat(
    netlist: Netlist,
    manifest: DomainManifest,
    floors: dict[str, tuple[str, float]],
    resolved: dict[str, ResolvedInstance],
    ref_of_path: dict[str, str],
) -> list[VoltageDomainFinding]:
    name_to_code = build_name_to_code(netlist)

    ref_voltage: dict[str, float] = {}
    ref_path: dict[str, str] = {}
    for path, inst in resolved.items():
        if inst.voltage_rating is None:
            continue
        ref = ref_of_path.get(path)
        if ref is None:
            continue
        ref_voltage[ref] = inst.voltage_rating
        ref_path[ref] = path

    findings: list[VoltageDomainFinding] = []
    for net_name, (domain, floor) in floors.items():
        code = name_to_code.get(net_name)
        if code is None:
            raise GateError(
                f"domain {domain!r} declares net {net_name!r} which does "
                "not exist in the compiled netlist -- stale manifest "
                "(check_domain_partition.py would also fail closed on "
                "this same condition)"
            )
        for ref, _pin in netlist.net_nodes.get(code, []):
            rating = ref_voltage.get(ref)
            if rating is None:
                continue
            if rating < floor:
                findings.append(
                    VoltageDomainFinding(domain, floor, net_name, ref_path[ref], ref, rating)
                )

    # A multi-pin part with >1 pin on the same named net would otherwise
    # report once per pin; de-duplicate to one finding per (net, ref).
    seen: set[tuple[str, str]] = set()
    deduped: list[VoltageDomainFinding] = []
    for f in findings:
        key = (f.net_name, f.ref)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(f)
    return sorted(deduped, key=lambda f: (f.domain, f.net_name, f.ref))


# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------


@dataclass
class AllowlistEntry:
    check: str
    key: dict[str, str]
    reason: str


def load_allowlist(path: Path) -> list[AllowlistEntry]:
    if not path.is_file():
        return []
    raw_text = path.read_text(encoding="utf-8")
    if not raw_text.strip():
        return []
    import yaml

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise GateError(f"allowlist is not valid YAML: {exc}") from exc
    if data is None:
        return []
    if not isinstance(data, dict) or "allowlist" not in data:
        raise GateError(
            f"{path}: must be a mapping with a top-level 'allowlist' key"
        )
    entries_raw = data["allowlist"]
    if not isinstance(entries_raw, list):
        raise GateError(f"{path}: 'allowlist' must be a list")
    entries: list[AllowlistEntry] = []
    for e in entries_raw:
        if not isinstance(e, dict):
            raise GateError(f"{path}: allowlist entry must be a mapping: {e!r}")
        check = e.get("check")
        reason = e.get("reason")
        if not check or not isinstance(check, str):
            raise GateError(f"{path}: allowlist entry missing 'check': {e!r}")
        if not reason or not isinstance(reason, str):
            raise GateError(f"{path}: allowlist entry missing 'reason': {e!r}")
        key = {k: str(v) for k, v in e.items() if k not in ("check", "reason")}
        if not key:
            raise GateError(
                f"{path}: allowlist entry for check {check!r} has no key "
                "fields beyond 'check'/'reason' -- would match every finding"
            )
        entries.append(AllowlistEntry(check=check, key=key, reason=reason))
    return entries


def _allowlisted(check: str, key: dict[str, str], entries: list[AllowlistEntry]) -> str | None:
    """Return the matching entry's reason, or None if not allowlisted."""
    for e in entries:
        if e.check == check and e.key == key:
            return e.reason
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(
    netlist_path: Path,
    domain_manifest_path: Path,
    src_dir: Path,
    allowlist_path: Path,
    skip_freshness: bool = False,
) -> int:
    try:
        if not skip_freshness:
            check_netlist_freshness(netlist_path, src_dir)
        netlist = parse_netlist(netlist_path)
        manifest = load_domain_manifest(domain_manifest_path)
        allowlist = load_allowlist(allowlist_path)

        ato_paths = [src_dir / name for name in ATO_SOURCE_FILES]
        classes = parse_ato_classes(ato_paths)
        resolved = resolve_instances(classes, root="Top")
        ref_of_path = path_to_ref(netlist)
        power_pins = find_power_pins(classes, resolved)
        floors = compute_net_voltage_floors(manifest)

        # Anti-vacuous-truth: confirm real, non-empty data before any
        # verdict is trusted (METHODOLOGY.md Sec 4/5), explicit checks (not
        # `assert`) so this cannot be compiled away under `python -O`.
        if len(netlist.nets) == 0:
            raise GateError("no nets in netlist (should have been caught earlier)")
        if len(classes) == 0:
            raise GateError("elec/src/*.ato parsed to zero classes (parser failure)")
        if len(resolved) == 0:
            raise GateError("zero instances resolved from Top (should have been caught earlier)")

        single_pin = check_single_pin_nets(netlist)
        power = check_unconnected_power_pins(netlist, power_pins, ref_of_path)
        voltage = check_voltage_domain_compat(netlist, manifest, floors, resolved, ref_of_path)
    except GateError as exc:
        print("=== NETLIST-STAGE CHECKS GATE ERROR ===", file=sys.stderr)
        print(f"Reason: {exc}", file=sys.stderr)
        print(
            "GATE RESULT: ERROR -- not PASSED, not a violation. The gate "
            "could not run a trustworthy check.",
            file=sys.stderr,
        )
        gh = get_github_summary_path()
        if gh:
            with open(gh, "a") as f:
                f.write("### Netlist-Stage Checks Gate -- GATE ERROR\n")
                f.write(f"{exc}\n")
        return EXIT_GATE_ERROR

    print(f"Netlist: {netlist_path}")
    print(f"Domain manifest: {domain_manifest_path}")
    print(
        f"Checked {len(netlist.nets)} compiled nets / {len(netlist.components)} "
        f"components; {len(resolved)} instances resolved from elec/src/*.ato "
        f"({sum(1 for r in resolved.values() if r.voltage_rating is not None)} "
        f"with a known voltage_rating); {len(power_pins)} declared power/"
        f"ground pins across the design. Explicitly-named net voltage "
        f"floors checked: "
        + ", ".join(
            f"{net}={v:g}V ({d})" for net, (d, v) in sorted(floors.items())
        )
        + "."
    )

    def _partition(findings: list, check: str, key_fn) -> tuple[list, list[tuple]]:
        live, allowed = [], []
        for f in findings:
            reason = _allowlisted(check, key_fn(f), allowlist)
            if reason is not None:
                allowed.append((f, reason))
            else:
                live.append(f)
        return live, allowed

    live_single, allowed_single = _partition(
        single_pin, "single_pin_net", lambda f: {"net": f.net_name}
    )
    live_power, allowed_power = _partition(
        power, "unconnected_power_pin", lambda f: {"instance_path": f.instance_path, "pin": f.pin}
    )
    live_voltage, allowed_voltage = _partition(
        voltage, "voltage_domain", lambda f: {"instance_path": f.instance_path, "net": f.net_name}
    )

    total_live = len(live_single) + len(live_power) + len(live_voltage)
    total_allowed = len(allowed_single) + len(allowed_power) + len(allowed_voltage)

    gh = get_github_summary_path()
    gh_lines: list[str] = []

    if total_live == 0:
        print(
            f"\nPASSED -- 0 non-allowlisted findings "
            f"({total_allowed} allowlisted, {len(single_pin)} single-pin "
            f"net(s), {len(power)} unconnected-power-pin finding(s), "
            f"{len(voltage)} voltage-domain finding(s) total)"
        )
        if gh:
            with open(gh, "a") as f:
                f.write("### Netlist-Stage Checks Gate -- PASSED\n")
                f.write(f"0 non-allowlisted findings ({total_allowed} allowlisted).\n")
        return EXIT_OK

    print(f"\n=== SINGLE-PIN NETS: {len(single_pin)} ({len(live_single)} live) ===")
    for f in live_single:
        line = f"  {f.net_name!r}: only {f.ref}.{f.pin} connects to it"
        print(line)
        gh_lines.append(f"- [single_pin_net] `{f.net_name}`: only {f.ref}.{f.pin}")
    for f, reason in allowed_single:
        print(f"  (allowlisted) {f.net_name!r}: only {f.ref}.{f.pin} -- {reason}")

    print(
        f"\n=== UNCONNECTED POWER PINS: {len(power)} ({len(live_power)} live) ==="
    )
    for f in live_power:
        line = f"  {f.instance_path} ({f.ref}.{f.pin}, signal {f.signal_name!r}): {f.reason}"
        print(line)
        gh_lines.append(
            f"- [unconnected_power_pin] `{f.instance_path}` ({f.ref}.{f.pin} "
            f"{f.signal_name}): {f.reason}"
        )
    for f, reason in allowed_power:
        print(
            f"  (allowlisted) {f.instance_path} ({f.ref}.{f.pin}, "
            f"{f.signal_name!r}): {f.reason} -- {reason}"
        )

    print(
        f"\n=== VOLTAGE-DOMAIN COMPATIBILITY: {len(voltage)} ({len(live_voltage)} live) ==="
    )
    for f in live_voltage:
        line = (
            f"  {f.instance_path} ({f.ref}) on {f.domain} net {f.net_name!r} "
            f"(floor {f.floor_voltage:g}V): voltage_rating={f.voltage_rating:g}V "
            f"< floor"
        )
        print(line)
        gh_lines.append(
            f"- [voltage_domain] `{f.instance_path}` ({f.ref}) on {f.domain} "
            f"`{f.net_name}`: rated {f.voltage_rating:g}V < {f.floor_voltage:g}V floor"
        )
    for f, reason in allowed_voltage:
        print(
            f"  (allowlisted) {f.instance_path} ({f.ref}) on {f.domain} "
            f"{f.net_name!r}: {f.voltage_rating:g}V < {f.floor_voltage:g}V -- {reason}"
        )

    if gh:
        with open(gh, "a") as f:
            f.write("### Netlist-Stage Checks Gate -- FAILED\n")
            f.write(
                f"{total_live} non-allowlisted finding(s) "
                f"({total_allowed} allowlisted): {len(live_single)} single-pin "
                f"net(s), {len(live_power)} unconnected-power-pin(s), "
                f"{len(live_voltage)} voltage-domain violation(s)\n\n"
            )
            for line in gh_lines[:200]:
                f.write(line + "\n")

    print(
        f"\nFAILED -- {total_live} non-allowlisted finding(s) "
        f"({total_allowed} allowlisted): {len(live_single)} single-pin net(s), "
        f"{len(live_power)} unconnected-power-pin(s), "
        f"{len(live_voltage)} voltage-domain violation(s)"
    )
    return EXIT_VIOLATION


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--netlist", type=Path, default=DEFAULT_NETLIST)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_DOMAIN_MANIFEST)
    parser.add_argument("--src-dir", type=Path, default=DEFAULT_SRC_DIR)
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    parser.add_argument(
        "--skip-freshness-check",
        action="store_true",
        help="Skip the netlist-vs-source staleness check (test fixtures only).",
    )
    args = parser.parse_args()
    sys.exit(
        run(args.netlist, args.manifest, args.src_dir, args.allowlist, args.skip_freshness_check)
    )


if __name__ == "__main__":
    main()
