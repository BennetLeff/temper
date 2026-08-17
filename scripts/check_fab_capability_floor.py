#!/usr/bin/env python3
"""Fab-capability floor gate: board via geometry and the "Via hole
clearance" DRU rule must never fall below JLCPCB's published 2oz-multilayer
manufacturability floor.

Why this gate exists
---------------------
``docs/evidence/2026-08-13-jlcpcb-fab-capability-envelope.md`` measured that
every via on the board (44/44) failed JLCPCB's real, published PTH
annular-ring floor (0.254mm at 2oz), and that the repo's own "Via hole
clearance" DRU rule (0.25mm, ``scripts/generate_kicad_dru.py``) was below
JLCPCB's published PTH-to-track absolute minimum (0.28mm) *independent of
copper weight* -- the repo's own rule could never have caught this class of
defect, because it was itself below the fab floor. Both were fixed in the
same PR that adds this gate (via pad geometry raised to a 0.3mm annular
ring across every via family/net-class/generator constant; the DRU rule
raised 0.25mm -> 0.28mm). This gate exists so neither regresses silently on
a future board/generator change -- a bare kicad-cli DRC run cannot catch
this, because kicad-cli only checks the board against *this repo's own*
DRU rule, and a DRU rule that is itself below the fab floor happily passes
geometry the fab cannot build.

**This is a manufacturability check, not a safety check.** It never reads
or compares against any IEC-60335 creepage/clearance figure
(``HV_INTERNAL_CLEARANCE_MM``, ``HV_CREEPAGE_ENFORCED_MM``, etc.) -- those
are out of scope by construction (see ``scripts/generate_kicad_dru.py``'s
own module comments for that boundary).

Single source of truth for the numeric floors
-----------------------------------------------
``docs/hardware/FAB_CAPABILITY.md`` sec.5 -- a fenced ``yaml`` block within
that markdown file, the SAME figures as that document's cited sec.1 table,
just in a form this script can load without parsing prose. This script
hardcodes no fab figure itself; every threshold below is read from that
file at run time. If the file, the fenced block, or a required key is
missing, this gate fails closed (exit 2) rather than falling back to a
baked-in number.

Properties checked
-------------------
P1  Every via in ``pcb/temper.kicad_pcb`` (literal ``(size ...) (drill
    ...)`` parse, exhaustive by construction) has an annular ring
    ``(size - drill) / 2`` at or above ``min_annular_ring_mm``.
P2  Every ``TEMPER_NET_CLASSES`` entry's ``via_diameter``/``via_drill``
    pair (``core/design_rules.py``) yields a ring at or above the floor --
    the router's own net-class via-sizing table must not reintroduce a
    sub-floor family even if none is currently routed.
P2b Every ``netclass_rules.yaml`` class's ``via_diameter``/``via_drill``
    pair (``packages/temper-placer/configs/netclass_rules.yaml`` -- the
    file ``router_v6`` actually consumes at route time) yields a ring at
    or above the floor. This is a separate table from P2 because the two
    files drifted once already in exactly this gate's direction: the
    2026-08-13 fab-floor sweep fixed ``TEMPER_NET_CLASSES`` to a 0.3mm
    ring everywhere but ``netclass_rules.yaml``'s ``HighVoltageSignal``
    stayed 0.8/0.4 (0.2mm ring) -- a green P2 with a router emitting 69
    sub-floor vias per route. Both homes must pass.
P2c ``io/_parse_nets.py``'s ``default_via_diameter``/``default_via_drill``
    literals (the defaults ``parse_kicad_pcb`` bakes into
    ``pcb.design_rules``, which the route's via placement reads for
    unclassified nets) yield a ring at or above the floor. Missed by the
    same 2026-08-13 sweep: it stayed 0.8/0.4 (0.2mm ring) and produced
    34 annular_width violations on the 2026-08-16 fab-fixed route, all
    blind vias on nets with no netclass assignment.
P3  ``router_v6/_ground_plane.py`` and ``router_v6/_power_islands.py``'s
    ``VIA_SIZE_MM``/``VIA_DRILL_MM`` constants (the two confirmed literal
    generators of the board's larger via family) yield a ring at or above
    the floor.
P4  ``generate_kicad_dru.py``'s ``VIA_HOLE_CLEARANCE_MM`` constant is at or
    above ``min_hole_to_copper_pth_to_track_abs_min_mm``.
P5  The DRU text ``generate_kicad_dru.generate_dru()`` actually emits
    carries that same "Via hole clearance" ``hole_clearance`` minimum --
    guards against the constant being renamed or the emission site
    reverting to a literal out from under P4.

What this gate deliberately does NOT do
-----------------------------------------
It does not re-derive JLCPCB's published figures (that is
``docs/evidence/2026-08-13-jlcpcb-fab-capability-envelope.md``'s job, done
once, cited here) and it does not touch trace width/clearance/creepage --
see the sibling ``latent risk`` rows FAB_CAPABILITY.md sec.4 documents
(``FinePitch``/``Differential`` trace width and same-footprint clearance),
explicitly out of this gate's scope. It also does not fix or re-check the
90 pre-existing ``hole_clearance`` (hole-to-*neighboring-copper*) DRC
findings -- those are a routing-congestion problem, not a via-pad-vs-
own-drill geometry problem (see FAB_CAPABILITY.md sec.4's own note), and
are scoped to a separate rerouting effort.

Exit codes: 0 pass, 1 violation, 2 could not run (missing/malformed input).
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FAB_CAPABILITY_DOC = REPO_ROOT / "docs" / "hardware" / "FAB_CAPABILITY.md"
KICAD_PCB = REPO_ROOT / "pcb" / "temper.kicad_pcb"
DESIGN_RULES = (
    REPO_ROOT / "packages" / "temper-placer" / "src" / "temper_placer" / "core" / "design_rules.py"
)
ROUTER_V6 = REPO_ROOT / "packages" / "temper-placer" / "src" / "temper_placer" / "router_v6"
GENERATOR_CONSTANT_FILES = ("_ground_plane.py", "_power_islands.py")

_TOL = 1e-9


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 2)."""


# ---------------------------------------------------------------------------
# SSOT: docs/hardware/FAB_CAPABILITY.md's fenced yaml block
# ---------------------------------------------------------------------------


def load_fab_floors(doc_path: Path | None = None) -> dict[str, float]:
    """Parse the ``jlcpcb_2oz_multilayer`` fenced ``yaml`` block out of
    ``docs/hardware/FAB_CAPABILITY.md`` sec.5. Raises ``GateError`` (fail
    closed) if the file, the fence, or the expected top-level key is
    missing/malformed -- this script must never fall back to a hardcoded
    number.

    ``doc_path`` defaults to the LIVE module global ``FAB_CAPABILITY_DOC``,
    resolved at call time (not bound as a mutable default argument) so
    ``monkeypatch.setattr(gate, "FAB_CAPABILITY_DOC", ...)`` in tests
    actually takes effect."""
    if doc_path is None:
        doc_path = FAB_CAPABILITY_DOC
    if not doc_path.is_file():
        raise GateError(f"{doc_path} not found")

    text = doc_path.read_text(encoding="utf-8")
    match = re.search(r"```yaml\n(.*?\n)```", text, re.DOTALL)
    if not match:
        raise GateError(
            f"{doc_path} has no fenced ```yaml``` block -- the gate-input "
            "SSOT (sec.5) is missing or was reformatted out from under this "
            "gate"
        )

    import yaml

    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as e:
        raise GateError(f"{doc_path}'s fenced yaml block is not valid YAML: {e}") from e

    if not isinstance(data, dict) or "jlcpcb_2oz_multilayer" not in data:
        raise GateError(
            f"{doc_path}'s fenced yaml block has no top-level "
            "'jlcpcb_2oz_multilayer' key"
        )

    floors = data["jlcpcb_2oz_multilayer"]
    if not isinstance(floors, dict):
        raise GateError(f"{doc_path}'s 'jlcpcb_2oz_multilayer' is not a mapping")

    return {str(k): float(v) for k, v in floors.items()}


def _require(floors: dict[str, float], key: str) -> float:
    if key not in floors:
        raise GateError(
            f"{FAB_CAPABILITY_DOC} sec.5's jlcpcb_2oz_multilayer block has no "
            f"'{key}' entry"
        )
    return floors[key]


# ---------------------------------------------------------------------------
# P1: real board via geometry
# ---------------------------------------------------------------------------


def board_via_rings(pcb_path: Path | None = None) -> list[tuple[float, float, float]]:
    """Return ``(size, drill, ring)`` for every ``(via ...)`` block in
    ``pcb/temper.kicad_pcb``, via literal balanced-paren scanning (no DRC
    engine, no kiutils round-trip -- exhaustive by construction, mirrors
    the independent measurement technique in the 2026-08-13 evidence doc).

    ``pcb_path`` defaults to the LIVE module global ``KICAD_PCB``, resolved
    at call time (see ``load_fab_floors``'s identical note)."""
    if pcb_path is None:
        pcb_path = KICAD_PCB
    if not pcb_path.is_file():
        raise GateError(f"{pcb_path} not found")

    text = pcb_path.read_text(encoding="utf-8")
    results: list[tuple[float, float, float]] = []
    for m in re.finditer(r"\(via\b", text):
        start = m.start()
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
            raise GateError(f"unbalanced (via ...) block at offset {start} in {pcb_path}")
        block = text[start:end]
        size_m = re.search(r"\(size\s+([\d.]+)\)", block)
        drill_m = re.search(r"\(drill\s+([\d.]+)\)", block)
        if size_m is None or drill_m is None:
            raise GateError(f"(via ...) block missing size/drill: {block[:120]!r}")
        size, drill = float(size_m.group(1)), float(drill_m.group(1))
        results.append((size, drill, (size - drill) / 2.0))
    return results


# ---------------------------------------------------------------------------
# P2: TEMPER_NET_CLASSES via_diameter/via_drill
# ---------------------------------------------------------------------------


def net_class_via_rings() -> dict[str, tuple[float, float, float]]:
    """Return ``{class_name: (via_diameter, via_drill, ring)}`` for every
    live ``TEMPER_NET_CLASSES`` entry, plus the ``__default__`` fallback
    used by ``create_temper_design_rules()``."""
    src = REPO_ROOT / "packages" / "temper-placer" / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    try:
        from temper_placer.core.design_rules import TEMPER_NET_CLASSES, create_temper_design_rules
    except ImportError as e:
        raise GateError(
            f"could not import temper_placer.core.design_rules -- is the "
            f"environment synced (`uv sync`)? ({e})"
        ) from e

    out: dict[str, tuple[float, float, float]] = {}
    for name, rules in TEMPER_NET_CLASSES.items():
        dia, drill = float(rules.via_diameter), float(rules.via_drill)
        out[name] = (dia, drill, (dia - drill) / 2.0)

    dr = create_temper_design_rules()
    dia, drill = float(dr.default_via_diameter), float(dr.default_via_drill)
    out["__default__"] = (dia, drill, (dia - drill) / 2.0)
    return out


def yaml_net_class_via_rings() -> dict[str, tuple[float, float, float]]:
    """Return ``{class_name: (via_diameter, via_drill, ring)}`` for every
    class in ``packages/temper-placer/configs/netclass_rules.yaml`` -- the
    file ``router_v6`` actually consumes at route time (loaded via
    ``io/netclass_loader.py`` -> ``temper-design-bundle``'s
    ``load_netclass_rules``), as opposed to ``TEMPER_NET_CLASSES`` in
    ``core/design_rules.py`` which P2's ``net_class_via_rings`` reads.

    Why this is a separate table and not folded into
    ``net_class_via_rings``: the two files drifted once already, in exactly
    the direction this gate exists to catch -- ``HighVoltageSignal``
    (created 2026-08-13 by the same commit that swept every OTHER class
    to a 0.3mm annular ring) carried ``0.8/0.4`` (0.2mm ring, below the
    0.254mm floor) in netclass_rules.yaml and kicad_pro while
    ``TEMPER_NET_CLASSES`` already had the correct ``1.0/0.4``. P2 checked
    only the design_rules.py home, so the router kept emitting sub-floor
    vias for months (69 annular_width errors on the 2026-08-16 capstone
    route, all 0.8/0.4 HighVoltageSignal vias) with a green gate. The
    router's real via sizing comes from THIS file, so this gate must read
    it or it is checking the wrong home (handoff mechanism 1: one fact,
    many homes)."""
    path = REPO_ROOT / "packages" / "temper-placer" / "configs" / "netclass_rules.yaml"
    if not path.is_file():
        raise GateError(f"{path} not found")
    import yaml

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise GateError(f"{path} is not valid YAML: {e}") from e
    classes = data.get("classes") if isinstance(data, dict) else None
    if not isinstance(classes, dict) or not classes:
        raise GateError(f"{path} has no non-empty 'classes' mapping")

    out: dict[str, tuple[float, float, float]] = {}
    for name, body in classes.items():
        if not isinstance(body, dict):
            continue
        dia = body.get("via_diameter")
        drill = body.get("via_drill")
        if dia is None or drill is None:
            continue
        dia, drill = float(dia), float(drill)
        out[str(name)] = (dia, drill, (dia - drill) / 2.0)
    if not out:
        raise GateError(f"{path}: no class carries both via_diameter and via_drill")
    return out


# ---------------------------------------------------------------------------
# P3: router_v6 generator constants
# ---------------------------------------------------------------------------


def generator_constant_rings() -> dict[str, tuple[float, float, float]]:
    """AST-scan ``VIA_SIZE_MM``/``VIA_DRILL_MM`` module-level assignments in
    the two confirmed literal via generators
    (``router_v6/_ground_plane.py``, ``router_v6/_power_islands.py``). AST,
    not import, so a value is caught even if the module has an import-time
    side effect this gate's environment cannot satisfy."""
    out: dict[str, tuple[float, float, float]] = {}
    for fname in GENERATOR_CONSTANT_FILES:
        path = ROUTER_V6 / fname
        if not path.is_file():
            raise GateError(f"{path} not found")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        size_val: float | None = None
        drill_val: float | None = None
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not (
                isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, (int, float))
                and not isinstance(node.value.value, bool)
            ):
                continue
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id == "VIA_SIZE_MM":
                    size_val = float(node.value.value)
                elif target.id == "VIA_DRILL_MM":
                    drill_val = float(node.value.value)
        if size_val is None or drill_val is None:
            raise GateError(
                f"{path} has no module-level VIA_SIZE_MM/VIA_DRILL_MM "
                "numeric-literal assignment -- gate cannot verify this "
                "generator's via geometry"
            )
        out[fname] = (size_val, drill_val, (size_val - drill_val) / 2.0)
    return out


# ---------------------------------------------------------------------------
# P4/P5: "Via hole clearance" DRU rule
# ---------------------------------------------------------------------------


def parse_nets_via_defaults() -> dict[str, tuple[float, float, float]]:
    """AST-scan ``io/_parse_nets.py``'s module-level
    ``default_via_diameter``/``default_via_drill`` numeric literals -- the
    defaults ``parse_kicad_pcb`` bakes into ``pcb.design_rules``, which
    the route's via placement reads for nets with no netclass assignment.
    AST, not import (same rationale as ``generator_constant_rings``: the
    module pulls in the whole parse stack). Missed by the 2026-08-13
    sweep: stayed 0.8/0.4 (0.2mm ring) and produced 34 annular_width
    violations on the 2026-08-16 fab-fixed route."""
    path = REPO_ROOT / "packages" / "temper-placer" / "src" / "temper_placer" / "io" / "_parse_nets.py"
    if not path.is_file():
        raise GateError(f"{path} not found")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    size_val: float | None = None
    drill_val: float | None = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not (
            isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, (int, float))
            and not isinstance(node.value.value, bool)
        ):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id == "default_via_diameter":
                size_val = float(node.value.value)
            elif target.id == "default_via_drill":
                drill_val = float(node.value.value)
    if size_val is None or drill_val is None:
        raise GateError(
            f"{path} has no module-level default_via_diameter/"
            "default_via_drill numeric-literal assignment -- gate cannot "
            "verify this parser's via defaults"
        )
    return {"_parse_nets_default": (size_val, drill_val, (size_val - drill_val) / 2.0)}


def dru_via_hole_clearance_constant() -> float:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        from generate_kicad_dru import VIA_HOLE_CLEARANCE_MM
    except ImportError as e:
        raise GateError(f"could not import scripts/generate_kicad_dru.py: {e}") from e
    return float(VIA_HOLE_CLEARANCE_MM)


def dru_emitted_via_hole_clearance() -> float | None:
    """Parse the emitted "Via hole clearance" rule back out of the
    generated ``.kicad_dru`` text (never the gitignored file on disk, so
    this works in a fresh clone -- mirrors
    ``check_router_clearance_floor.py``'s P3)."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from generate_kicad_dru import generate_dru

    text = generate_dru()
    match = re.search(
        r'\(rule "Via hole clearance"\s*\n\s*\(constraint hole_clearance \(min ([\d.]+)mm\)\)',
        text,
    )
    return float(match.group(1)) if match else None


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run() -> int:
    try:
        floors = load_fab_floors()
    except GateError as e:
        print(f"MISSING/MALFORMED INPUT: {e}")
        return 2

    ring_floor = _require(floors, "min_annular_ring_mm")
    hole_clearance_floor = _require(floors, "min_hole_to_copper_pth_to_track_abs_min_mm")
    print(f"Fab floor (docs/hardware/FAB_CAPABILITY.md sec.5): annular ring >= {ring_floor}mm, "
          f"hole_clearance >= {hole_clearance_floor}mm")

    failures: list[str] = []

    # P1
    try:
        vias = board_via_rings()
    except GateError as e:
        print(f"MISSING/MALFORMED INPUT: {e}")
        return 2
    below = [(s, d, r) for s, d, r in vias if r < ring_floor - _TOL]
    if below:
        for size, drill, ring in below:
            failures.append(
                f"P1: pcb/temper.kicad_pcb has a via (size {size}mm, drill "
                f"{drill}mm) with ring {ring:.4f}mm, below the {ring_floor}mm "
                "fab floor"
            )
    else:
        print(f"  P1 OK  {len(vias)} via(s) on pcb/temper.kicad_pcb, all >= {ring_floor}mm ring")

    # P2
    try:
        nc_rings = net_class_via_rings()
    except GateError as e:
        print(f"MISSING/MALFORMED INPUT: {e}")
        return 2
    nc_below = {n: v for n, v in nc_rings.items() if v[2] < ring_floor - _TOL}
    if nc_below:
        for name, (dia, drill, ring) in sorted(nc_below.items()):
            failures.append(
                f"P2: net class {name!r} via_diameter={dia}mm/via_drill={drill}mm "
                f"gives ring {ring:.4f}mm, below the {ring_floor}mm fab floor "
                "(core/design_rules.py TEMPER_NET_CLASSES or its default)"
            )
    else:
        print(f"  P2 OK  {len(nc_rings)} net-class via template(s), all >= {ring_floor}mm ring")

    # P2b: netclass_rules.yaml -- the file the ROUTER actually consumes at
    # route time (io/netclass_loader.py). See yaml_net_class_via_rings'
    # docstring for why this is a separate table: P2 alone checked only
    # design_rules.py and let HighVoltageSignal's sub-floor 0.8/0.4 slip
    # through for months while the router kept emitting it.
    try:
        yaml_rings = yaml_net_class_via_rings()
    except GateError as e:
        print(f"MISSING/MALFORMED INPUT: {e}")
        return 2
    yaml_below = {n: v for n, v in yaml_rings.items() if v[2] < ring_floor - _TOL}
    if yaml_below:
        for name, (dia, drill, ring) in sorted(yaml_below.items()):
            failures.append(
                f"P2b: netclass_rules.yaml class {name!r} "
                f"via_diameter={dia}mm/via_drill={drill}mm gives ring "
                f"{ring:.4f}mm, below the {ring_floor}mm fab floor (the file "
                "the router consumes at route time)"
            )
    else:
        print(
            f"  P2b OK  {len(yaml_rings)} netclass_rules.yaml via "
            f"template(s), all >= {ring_floor}mm ring"
        )

    # P2c: io/_parse_nets.py's defaults -- the values parse_kicad_pcb bakes
    # into pcb.design_rules, which the route's via placement reads for
    # unclassified nets. See parse_nets_via_defaults' docstring.
    try:
        parse_defaults = parse_nets_via_defaults()
    except GateError as e:
        print(f"MISSING/MALFORMED INPUT: {e}")
        return 2
    parse_below = {n: v for n, v in parse_defaults.items() if v[2] < ring_floor - _TOL}
    if parse_below:
        for name, (dia, drill, ring) in sorted(parse_below.items()):
            failures.append(
                f"P2c: {name} via_diameter={dia}mm/via_drill={drill}mm "
                f"gives ring {ring:.4f}mm, below the {ring_floor}mm fab "
                "floor (io/_parse_nets.py's pcb.design_rules defaults)"
            )
    else:
        print(
            f"  P2c OK  {len(parse_defaults)} io/_parse_nets.py default(s), "
            "all >= " + f"{ring_floor}mm ring"
        )

    # P3
    try:
        gen_rings = generator_constant_rings()
    except GateError as e:
        print(f"MISSING/MALFORMED INPUT: {e}")
        return 2
    gen_below = {n: v for n, v in gen_rings.items() if v[2] < ring_floor - _TOL}
    if gen_below:
        for fname, (size, drill, ring) in sorted(gen_below.items()):
            failures.append(
                f"P3: router_v6/{fname} VIA_SIZE_MM={size}mm/VIA_DRILL_MM="
                f"{drill}mm gives ring {ring:.4f}mm, below the {ring_floor}mm "
                "fab floor"
            )
    else:
        print(f"  P3 OK  {len(gen_rings)} generator constant(s), all >= {ring_floor}mm ring")

    # P4
    try:
        dru_const = dru_via_hole_clearance_constant()
    except GateError as e:
        print(f"MISSING/MALFORMED INPUT: {e}")
        return 2
    if dru_const < hole_clearance_floor - _TOL:
        failures.append(
            f"P4: generate_kicad_dru.py VIA_HOLE_CLEARANCE_MM={dru_const}mm, "
            f"below the {hole_clearance_floor}mm fab floor"
        )
    else:
        print(f"  P4 OK  generate_kicad_dru.py VIA_HOLE_CLEARANCE_MM = {dru_const}mm")

    # P5
    try:
        emitted = dru_emitted_via_hole_clearance()
    except GateError as e:
        print(f"MISSING/MALFORMED INPUT: {e}")
        return 2
    if emitted is None:
        failures.append(
            "P5: generated .kicad_dru text has no parseable 'Via hole "
            "clearance' hole_clearance rule"
        )
    elif emitted < hole_clearance_floor - _TOL:
        failures.append(
            f"P5: emitted 'Via hole clearance' rule is {emitted}mm, below "
            f"the {hole_clearance_floor}mm fab floor"
        )
    else:
        print(f"  P5 OK  emitted 'Via hole clearance' rule = {emitted}mm")

    if failures:
        print()
        print(f"FAIL: {len(failures)} violation(s)")
        for line in failures:
            print(f"  - {line}")
        return 1

    print()
    print("PASS: board via geometry and the 'Via hole clearance' DRU rule "
          "both meet the JLCPCB fab-capability floor")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
