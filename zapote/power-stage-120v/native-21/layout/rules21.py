"""Pairwise copper clearance under section.kicad_dru's D5 rules (for authoring checks).

clearance(a, b) -> mm, the same order of precedence as the rules file: SELV/PE vs HOT
8.0, tank node vs other HOT 5.0, different HOT potential groups 3.2, otherwise the
0.2 mm board floor. Component-local exceptions (same footprint, pad escapes) are not
modelled here; KiCad DRC remains the authority.
"""
import importlib.util
import sys
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


BARRIER = _m.wr.REINFORCED_MM
# stage 18: RES_A to SELV/PE on outer layers (DECISIONS item 7): 12.6 mm; inner layers keep BARRIER
RES_A_NETS = set(_m.RES_A_NETS)
RES_A_CREEPAGE = _m.RES_A_CREEPAGE_MM
if str(Path(__file__).resolve().parent) not in sys.path:     # some callers load this file by path (importlib)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from layers21 import OUTER  # noqa: E402,F401  (F.Cu, B.Cu from native-21/stackup.json)


def res_a_pair(a, b):
    """True for RES_A against SELV / PE (the 12.6 mm outer-layer creepage pair)."""
    return (a in RES_A_NETS and domain(b) in ("SELV", "PE")) or (b in RES_A_NETS and domain(a) in ("SELV", "PE"))


def clearance_on(a, b, layer):
    """clearance(a, b) on one copper layer: RES_A to SELV / PE is 12.6 mm on the outer layers."""
    c = clearance(a, b)
    return max(c, RES_A_CREEPAGE) if layer in OUTER and res_a_pair(a, b) else c


def barrier(a, b):
    """True when the pair is separated by the reinforced barrier (plan view, all layers)."""
    return {domain(a), domain(b)} in ({"SELV", "HOT"}, {"PE", "HOT"})
