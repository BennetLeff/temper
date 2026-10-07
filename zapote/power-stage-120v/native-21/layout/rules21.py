"""Pairwise copper clearance under section.kicad_dru's D5 rules (for authoring checks).

clearance(a, b) -> mm, the same order of precedence as the rules file: SELV/PE vs HOT
8.0, tank node vs other HOT 5.0, different HOT potential groups 3.2, otherwise the
0.2 mm board floor. Component-local exceptions (same footprint, pad escapes) are not
modelled here; KiCad DRC remains the authority.
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("wr21", Path(__file__).with_name("write_rules21.py"))
_m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m)
GROUP = {n: g for g, ns in _m.groups.items() for n in ns}
SELV = set(_m.SELV) | set(_m.wr.SELV_NC)
PE = set(_m.wr.PE)
TANK = set(_m.wr.TANK)
FLOOR = 0.2


def domain(n):
    if n in SELV:
        return "SELV"
    if n in PE:
        return "PE"
    if n in GROUP:
        return "HOT"
    return "NONE"


def clearance(a, b):
    if not a or not b or a == b:
        return 0.0 if a == b and a else FLOOR
    da, db = domain(a), domain(b)
    if {da, db} in ({"SELV", "HOT"}, {"PE", "HOT"}):
        return _m.wr.REINFORCED_MM
    if da == db == "HOT":
        if (a in TANK) != (b in TANK) or (a in TANK and b in TANK):
            return _m.wr.TANK_CREEPAGE_MM
        if GROUP[a] != GROUP[b]:
            return _m.wr.FUNCTIONAL_CREEPAGE_MM
    return FLOOR
