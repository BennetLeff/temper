#!/usr/bin/env python3
"""Router-vs-DRC clearance floor gate: the clearance the router *reserves*
for an unclassified net must never be below the clearance the DRC run
*grades* that net against.

Why this gate exists
--------------------
Between 2026-07-12 (``051152e7c``) and 2026-08-12 those two numbers were
different, in the direction that produces DRC errors by construction:

* ``scripts/generate_kicad_dru.py`` RULE 10 ``"Default routing"`` emits
  ``(constraint clearance (min 0.2mm))`` and applies to every pair where
  either side is a Track. It is the rule the board's clearance errors
  actually fire against -- 503 of 505 on the heatsink candidate.
* ``router_v6/_pipeline_core.py`` set ``dr.default_clearance_mm = 0.15``
  on the way into Stage 4, described in its own comment as "the SSOT
  Signal netclass". ``netclass_rules.yaml``'s ``Signal`` class has no
  counterpart in ``pcb/temper.kicad_pro`` at all and no board net resolves
  to it (measured 0/684 net occurrences), so 0.15 was not any net's
  requirement -- it was a global relaxation of the fallback.

Stage 4's A* reserves ``trace_width + clearance`` around routed copper
(``_astar_reconstruct.py``'s ``_mark_route_blocked``), so a 0.15 floor put
two 0.25mm Default tracks 0.40mm centre-to-centre: an edge gap of exactly
0.1500mm against a 0.2000mm rule. On the heatsink candidate board, 136 of
505 ``clearance`` errors were that one value to four decimal places and
another 149 were its 45-degree corner case (0.4472mm centre distance ->
0.1972mm gap) -- together 56% of the board's clearance errors, and 80% of
the x[40,60) congestion band's. Full measurement:
``docs/evidence/2026-08-12-clearance-congestion-band.md``.

The defect is not detectable from either file alone. Each is internally
consistent and each cites a plausible source; only the *pair* is wrong.
That is what this gate checks.

Properties
----------
P1  ``generate_kicad_dru.DEFAULT_ROUTING_CLEARANCE_MM`` equals
    ``netclass_rules.yaml``'s ``default_clearance_mm``.
P2  It also equals ``pcb/temper.kicad_pro``'s ``Default`` net-class
    ``clearance``.
P3  The generated ``.kicad_dru`` text really carries that number in its
    ``Default routing`` rule (guards against the constant being renamed
    out of the emitter).
P4  No assignment anywhere in ``router_v6/`` writes a literal below the
    floor into ``default_clearance`` / ``default_clearance_mm``. Checked by
    AST, not grep, so a reformatted or renamed-variable reintroduction is
    still caught.
P5  The ``DesignRules`` the router pipeline actually builds from a board
    (``io/_parse_nets.py::_extract_design_rules``) reports a
    ``default_clearance_mm`` at or above the floor.

What this gate deliberately does NOT do
---------------------------------------
It does not decide what the floor should *be*. Raising or lowering
``DEFAULT_ROUTING_CLEARANCE_MM`` is a fabrication decision; this gate only
asserts that whatever it is, the router and the DRC agree on it. It also
says nothing about per-class clearances (FinePitch 0.1mm, GateDrive
0.25mm, HV 2.0/6.0mm) -- those are resolved per net by
``get_rules_for_net`` and are covered by
``scripts/check_netclass_class_param_correspondence.py``.

Exit codes: 0 pass, 1 violation, 2 could not run (missing input).
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
NETCLASS_RULES = REPO_ROOT / "packages" / "temper-placer" / "configs" / "netclass_rules.yaml"
KICAD_PRO = REPO_ROOT / "pcb" / "temper.kicad_pro"
ROUTER_V6 = REPO_ROOT / "packages" / "temper-placer" / "src" / "temper_placer" / "router_v6"

_CLEARANCE_ATTRS = ("default_clearance", "default_clearance_mm")
# Floating point: every figure involved is a two-decimal millimetre value.
_TOL = 1e-9


def _floor_mm() -> float:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from generate_kicad_dru import DEFAULT_ROUTING_CLEARANCE_MM

    return float(DEFAULT_ROUTING_CLEARANCE_MM)


def _yaml_default_clearance() -> float | None:
    import yaml

    data = yaml.safe_load(NETCLASS_RULES.read_text(encoding="utf-8"))
    value = data.get("default_clearance_mm")
    return None if value is None else float(value)


def _kicad_pro_default_clearance() -> float | None:
    data = json.loads(KICAD_PRO.read_text(encoding="utf-8"))
    for cls in data.get("net_settings", {}).get("classes", []):
        if cls.get("name") == "Default":
            value = cls.get("clearance")
            return None if value is None else float(value)
    return None


def _dru_default_routing_clearance() -> float | None:
    """Parse the emitted ``Default routing`` rule back out of the generated
    ``.kicad_dru`` text. Reads the generator's output, never the gitignored
    ``pcb/temper.kicad_dru`` on disk, so the gate works in a fresh clone."""
    import re

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from generate_kicad_dru import generate_dru

    text = generate_dru()
    match = re.search(
        r'\(rule "Default routing"\s*\n[^\n]*\n\s*\(constraint clearance \(min ([\d.]+)mm\)\)',
        text,
    )
    return float(match.group(1)) if match else None


def _literal_clearance_writes() -> list[tuple[Path, int, str, float]]:
    """Every ``<expr>.default_clearance[_mm] = <numeric literal>`` in
    ``router_v6/``, as ``(path, lineno, attr, value)``."""
    found: list[tuple[Path, int, str, float]] = []
    for path in sorted(ROUTER_V6.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - a broken file is not this gate's job
            continue
        for node in ast.walk(tree):
            targets: list[ast.expr] = []
            value: ast.expr | None = None
            if isinstance(node, ast.Assign):
                targets, value = list(node.targets), node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets, value = [node.target], node.value
            if value is None or not isinstance(value, ast.Constant):
                continue
            if not isinstance(value.value, (int, float)) or isinstance(value.value, bool):
                continue
            for target in targets:
                if isinstance(target, ast.Attribute) and target.attr in _CLEARANCE_ATTRS:
                    found.append((path, node.lineno, target.attr, float(value.value)))
    return found


def _parsed_board_default_clearance() -> float | None:
    src = REPO_ROOT / "packages" / "temper-placer" / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from temper_placer.io._parse_nets import _extract_design_rules

    board = REPO_ROOT / "pcb" / "temper.kicad_pcb"
    if not board.exists():
        return None
    rules = _extract_design_rules(None, [], board.read_text(encoding="utf-8"))
    return float(rules.default_clearance_mm)


def run() -> int:
    failures: list[str] = []

    if not NETCLASS_RULES.exists() or not KICAD_PRO.exists():
        print("MISSING INPUT: netclass_rules.yaml or pcb/temper.kicad_pro not found")
        return 2

    floor = _floor_mm()
    print(f"DRU default-routing clearance floor: {floor}mm")

    # P1
    yaml_value = _yaml_default_clearance()
    if yaml_value is None:
        failures.append("P1: netclass_rules.yaml has no default_clearance_mm")
    elif abs(yaml_value - floor) > _TOL:
        failures.append(
            f"P1: netclass_rules.yaml default_clearance_mm={yaml_value} != "
            f"DEFAULT_ROUTING_CLEARANCE_MM={floor}"
        )
    else:
        print(f"  P1 OK  netclass_rules.yaml default_clearance_mm = {yaml_value}")

    # P2
    pro_value = _kicad_pro_default_clearance()
    if pro_value is None:
        failures.append("P2: pcb/temper.kicad_pro has no 'Default' net class with a clearance")
    elif abs(pro_value - floor) > _TOL:
        failures.append(
            f"P2: pcb/temper.kicad_pro Default clearance={pro_value} != "
            f"DEFAULT_ROUTING_CLEARANCE_MM={floor}"
        )
    else:
        print(f"  P2 OK  temper.kicad_pro Default clearance = {pro_value}")

    # P3
    dru_value = _dru_default_routing_clearance()
    if dru_value is None:
        failures.append("P3: generated .kicad_dru has no parseable 'Default routing' rule")
    elif abs(dru_value - floor) > _TOL:
        failures.append(
            f"P3: emitted 'Default routing' rule is {dru_value}mm, "
            f"DEFAULT_ROUTING_CLEARANCE_MM is {floor}mm"
        )
    else:
        print(f"  P3 OK  emitted 'Default routing' rule = {dru_value}mm")

    # P4
    writes = _literal_clearance_writes()
    below = [w for w in writes if w[3] < floor - _TOL]
    for path, lineno, attr, value in below:
        failures.append(
            f"P4: {path.relative_to(REPO_ROOT)}:{lineno} assigns {attr} = {value}, "
            f"below the {floor}mm DRC floor -- the router would reserve less "
            f"than the DRC grades against, producing clearance errors by "
            f"construction"
        )
    if not below:
        print(
            f"  P4 OK  {len(writes)} literal default-clearance assignment(s) in "
            f"router_v6/, none below {floor}mm"
        )

    # P5
    try:
        parsed_value = _parsed_board_default_clearance()
    except Exception as exc:  # pragma: no cover - import/env failure, not a violation
        print(f"  P5 SKIP  could not build DesignRules from the board: {exc}")
        parsed_value = None
    else:
        if parsed_value is None:
            print("  P5 SKIP  pcb/temper.kicad_pcb not present")
        elif parsed_value < floor - _TOL:
            failures.append(
                f"P5: _extract_design_rules() yields default_clearance_mm="
                f"{parsed_value}, below the {floor}mm DRC floor"
            )
        else:
            print(f"  P5 OK  _extract_design_rules() default_clearance_mm = {parsed_value}")

    if failures:
        print()
        print(f"FAIL: {len(failures)} violation(s)")
        for line in failures:
            print(f"  - {line}")
        return 1

    print()
    print("PASS: router clearance floor agrees with the DRC clearance floor")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
