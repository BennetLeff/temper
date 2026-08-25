# provenance: commit=86cffca749c97e32eb8c8ba58b0999177dcad1b7 dirty=UNKNOWN (stamp added 2026-08-25; the file landed on main via #1418 (86cffca74) with no provenance line, which the Evidence provenance gate rejects. 86cffca74 is the commit that introduced it. dirty=UNKNOWN rather than a claim this stamp cannot support -- replace with the real measurement commit if it differs.)

"""Blast-radius measurement for `is_hv_net()` -- 2026-08-19.

Reproduces every number in docs/evidence/2026-08-19-is-hv-net-blast-radius.md.

    cd <repo root of a worktree with its own, freshly built .venv>
    ./.venv/bin/python scripts/generate_kicad_dru.py
    kicad-cli pcb drc --all-track-errors --severity-all --format json \
        -o drc.json pcb/temper.kicad_pcb
    env -u CONDA_PREFIX ./.venv/bin/python \
        docs/evidence/2026-08-19-is-hv-net-blast-radius.py

Reads only; never writes pcb/temper.kicad_pcb.
"""

import json
import os
import re
from collections import Counter

import temper_io_types as rs
import yaml

from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS, create_temper_design_rules
from temper_placer.core.net_classification import classify_net_type
from temper_placer.placer.cp_sat.gates import _HV_NET_PATTERNS, HV_LV_CREEPAGE_MM
from temper_placer.placer.cp_sat.gates import _is_hv_net as gate_is_hv
from temper_placer.router_v6 import clearance_check as cc
from temper_placer.router_v6._net_policy import _should_route
from temper_placer.router_v6._zone_pour_stitch import _zone_layers_for_net
from temper_placer.router_v6.constraints_design_rules import _classify_net
from temper_placer.router_v6.net_classification import is_ground_net as g6
from temper_placer.router_v6.net_classification import is_hv_net as h6
from temper_placer.router_v6.net_classification import is_power_net as p6

NETS = ["+170V_BUS", "DC_BUS_RTN", "hb-gnd", "tank-out", "tank.c_tank1-p2"]
EXTRA = ["ac_l", "ac_n", "AC_L", "AC_N"]
ALL = NETS + EXTRA

print("=" * 78)
print("A. NAME-PATTERN CLASSIFIER (temper_io_types / net_classification)")
print("=" * 78)
print(f"{'net':<20} {'gnd':>4} {'pwr':>4} {'hv':>4} {'core':>8} | {'pwr_v6':>7} {'v6':>8}")
for n in ALL:
    print(
        f"{n:<20} {int(rs.is_ground_net(n)):>4} {int(rs.is_power_net(n)):>4} "
        f"{int(rs.is_hv_net(n)):>4} {rs.classify_net_type(n):>8} | "
        f"{int(rs.is_power_net_v6(n)):>7} {rs.classify_net_type_v6(n):>8}"
    )

print()
print("=" * 78)
print("B. AUTHORITATIVE NETCLASS (design_rules.get_rules_for_net -> TEMPER_NET_ASSIGNMENTS)")
print("=" * 78)
dr = create_temper_design_rules()
print(f"{'net':<20} {'assignment':<20} {'class':<20} {'clear':>7} {'creep':>7} {'safety':>7}")
for n in ALL:
    r = dr.get_rules_for_net(n)
    print(
        f"{n:<20} {TEMPER_NET_ASSIGNMENTS.get(n, '(none)'):<20} {r.name:<20} "
        f"{r.clearance:>7} {getattr(r, 'creepage_mm', None)!s:>7} {getattr(r, 'safety_category', None)!s:>7}"
    )

print()
print("=" * 78)
print("C. pcb/temper.kicad_pro netclass_assignments (what kicad-cli DRC enforces)")
print("=" * 78)
pro = json.load(open("pcb/temper.kicad_pro"))
assigns = pro["net_settings"]["netclass_assignments"]
classes = {c["name"]: c for c in pro["net_settings"]["classes"]}
for n in ALL:
    cn = assigns.get(n)
    cl = classes.get(cn, {}).get("clearance") if cn else None
    print(f"{n:<20} -> {str(cn):<20} kicad clearance={cl}")

print()
print("=" * 78)
print("D. CONSUMER: placer/cp_sat/feedback._handle_clearance_violation")
print("   classify_net_type -> {ground:GND, power:Power, hv:HighVoltage, signal:Signal}")
print("=" * 78)
_map = {"ground": "GND", "power": "Power", "hv": "HighVoltage", "signal": "Signal"}
for n in ALL:
    now_cls = _map.get(classify_net_type(n), "Signal")
    now = dr.get_rules_for_net("", net_class=now_cls)
    correct_cls = dr.get_rules_for_net(n).name
    corr = dr.get_rules_for_net("", net_class=correct_cls)
    print(
        f"{n:<20} today={now_cls:<13} clr={now.clearance:<6} | correct={correct_cls:<18} clr={corr.clearance}"
    )

print()
print("=" * 78)
print("E. CONSUMER: placer/cp_sat/gates.IECCreepageGate._is_hv_net (local 7-name set)")
print("=" * 78)
print("HV_LV_CREEPAGE_MM =", HV_LV_CREEPAGE_MM)
for n in ALL:
    print(f"{n:<20} gate._is_hv_net={gate_is_hv(n)}")

print()
print("=" * 78)
print("F. CONSUMER: router_v6/clearance_check (domain-manifest OR keyword)")
print("=" * 78)
manifest = cc._load_manifest_hv_net_names()
for n in ALL:
    kw = cc._is_hv_keyword_match(n.upper())
    print(
        f"{n:<20} keyword={int(kw)} manifest={int(n in manifest)} "
        f"-> HV={int(kw or n in manifest)} class={cc._classify_net_class(n)}"
    )

print()
print("=" * 78)
print("G. CONSUMER: router_v6/_net_policy._should_route + zone eligibility")
print("=" * 78)
for n in ALL:
    recognised = p6(n) or g6(n) or h6(n)
    print(
        f"{n:<20} recognised(p/g/hv)={int(recognised)} zone_layers={_zone_layers_for_net(n)} "
        f"should_route={_should_route(n)}"
    )

print()
print("=" * 78)
print("H. CONSUMER: router_v6/constraints_design_rules._classify_net (ClearanceMatrix)")
print("=" * 78)
for n in ALL:
    print(f"{n:<20} _classify_net={_classify_net(n)}")

print()
print("=" * 78)
print("I. pair_clearance generated table (router DECISION-stage separation)")
print("=" * 78)
p = "configs/pair_clearance.generated.yaml"
if os.path.exists(p):
    d = yaml.safe_load(open(p))
    print("top-level keys:", list(d)[:10])
    print(json.dumps(d, default=str)[:1500])
else:
    print("MISSING", p)

# ---------------------------------------------------------------------------
# J. IECCreepageGate before/after on the REAL DRC report.
#
#   ./.venv/bin/python scripts/generate_kicad_dru.py
#   kicad-cli pcb drc --all-track-errors --severity-all --format json \
#       -o drc.json pcb/temper.kicad_pcb
#   env -u CONDA_PREFIX ./.venv/bin/python \
#       docs/evidence/2026-08-19-is-hv-net-blast-radius.py
#
# `drc.json` is read from the CWD; this block is skipped if it is absent.
# ---------------------------------------------------------------------------

if os.path.exists("drc.json"):
    print()
    print("=" * 78)
    print("J. IECCreepageGate HV<->LV filter, old classifier vs manifest-backed")
    print("=" * 78)

    _report = json.load(open("drc.json"))
    _NET_RE = re.compile(r"\[([^\]]+)\]")
    _mani = cc._load_manifest_hv_net_names()
    _man = yaml.safe_load(open("elec/domain_manifest.yaml"))["domains"]
    _HVD, _SELVD = set(_man["HV"]["nets"]), set(_man["SELV"]["nets"])

    def _nets_of(v):
        out = []
        for it in v.get("items", []):
            out += _NET_RE.findall(it.get("description", ""))
        return list(dict.fromkeys(out))

    def _old(n):
        return n in _HV_NET_PATTERNS

    def _new(n):
        return _old(n) or n in _mani or cc._is_hv_keyword_match(n.upper())

    print("total violations:", len(_report["violations"]))
    print(Counter(v["type"] for v in _report["violations"]).most_common())
    for _rule in ("clearance", "creepage"):
        for _label, _pred in (("old 7-name frozenset", _old), ("manifest-backed", _new)):
            _pairs = Counter()
            for v in _report["violations"]:
                if v["type"] != _rule:
                    continue
                _names = _nets_of(v)
                _hv = [n for n in _names if _pred(n)]
                _lv = [n for n in _names if not _pred(n) and n and not n[0].isdigit()]
                if _hv and _lv:
                    _pairs[tuple(sorted(set(_hv + _lv)))] += 1
            print(f"  rule={_rule:10} {_label:22} HV<->LV pairs = {sum(_pairs.values())}")
            if _rule == "clearance":
                for _p, _c in _pairs.most_common():
                    print("       ", _c, _p)
    # The strictest reading: declared-HV against declared-SELV, no keyword
    # heuristic involved at all.
    for _rule in ("clearance", "creepage"):
        _strict = sum(
            1
            for v in _report["violations"]
            if v["type"] == _rule
            and any(n in _HVD for n in _nets_of(v))
            and any(n in _SELVD for n in _nets_of(v))
        )
        print(f"  rule={_rule:10} DECLARED-HV <-> DECLARED-SELV pairs = {_strict}")
