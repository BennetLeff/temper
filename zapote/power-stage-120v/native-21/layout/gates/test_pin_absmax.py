#!/usr/bin/env python3
"""Controls for pin_absmax.py.

    python3 -I native-21/layout/gates/test_pin_absmax.py            # PIN_ABSMAX_DL=<dir with pdf/> also checks every quote

Synthetic cases (an in-memory netlist, resistor values and registry built from the real TPS70950 entry) exercise each verdict;
the last cases run the real frozen netlist with the real registry: it must FAIL on exactly the four TPS70950 EN pins.
"""
import copy
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pin_absmax", HERE / "pin_absmax.py")
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

fails = 0


def check(ok, name, detail=""):
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"   {detail}"))
    fails += 0 if ok else 1


UNIT = g.UNIT
REAL = json.loads((HERE / "pin_absmax_registry.json").read_text())
LDO = REAL["parts"]["TPS70950DBVR"]


def netlist(nets):
    """KiCad-style (export) text from {net: [(ref, pin), ...]}."""
    out = ['(export (version "E")', "  (nets"]
    for i, (n, members) in enumerate(nets.items(), 1):
        out.append(f'    (net (code "{i}") (name "{n}")')
        out += [f'      (node (ref "{r}") (pin "{p}") (pintype "stereo"))' for r, p in list(members) + [("CX", str(i))]]   # a probe cap: no net is single-node
        out.append("    )")
    return "\n".join(out) + "\n)"


def synth(nets, decl, parts=None, resistors=None, des_mpn=None):
    reg = {"resistor_tolerance": {"_default": {"tol": 0.01}}, "nets": decl, "parts": parts or {"TPS70950DBVR": LDO}}
    val = {r: (v, "R-GENERIC") for r, v in (resistors or {}).items()}
    mpn = {"U1": "TPS70950DBVR", **(des_mpn or {})}
    return g.check(UNIT, reg, netlist(nets), mpn, val)


def keys(r):
    return sorted(f"{x['part']}.{x['pin']}" for x in r["failures"])


def rail(ref, lo, hi, cite="synthetic"):
    return {"kind": "rail", "ref": ref, "lo": lo, "hi": hi, "cite": cite}


GND = {"kind": "root", "cite": "synthetic", "derive": "root"}
# ---- 1. EN tied to a 15 V rail fails (and the part-level reason names page 13 for the tie)
nets = {"gnd": [("U1", "2")], "vin": [("U1", "1"), ("U1", "3")], "out": [("U1", "5")], "nc": [("U1", "4")]}
decl = {"gnd": GND, "vin": rail("gnd", 14.4, 15.5), "out": rail("gnd", 4.95, 5.05)}
r = synth(nets, decl)
check(keys(r) == ["U1.3"] and not r["errors"], "synthetic EN tied to a 15 V rail FAILS on EN only", (keys(r), r["errors"]))
v = r["failures"][0]["violated"]
check(any(x.get("kind") == "forbidden tie" and x["page"] == 13 for x in v) and any(x["page"] == 4 and x["max"] == 7 for x in v),
      "the failure cites TI SBVS186H 6.1 p.4 (7 V) and 7.4 p.13 (do not tie EN to VIN)", v)
# ---- 2. EN from a divider passes; a divider that is too stiff still fails
nets = {"gnd": [("U1", "2"), ("R2", "2")], "vin": [("U1", "1"), ("R1", "1")], "en": [("U1", "3"), ("R1", "2"), ("R2", "1")],
        "out": [("U1", "5")], "nc": [("U1", "4")]}
decl = {"gnd": GND, "vin": rail("gnd", 14.4, 15.5), "out": rail("gnd", 4.95, 5.05),
        "en": {"kind": "divider", "top": "vin", "bottom": "gnd", "r_top": ["R1"], "r_bot": ["R2"], "cite": "synthetic", "derive": "R1 / R2"}}
r = synth(nets, decl, resistors={"R1": "200kohm", "R2": "100kohm"})
en = [x for x in r["rows"] if x["pin"] == "3"][0]
check(not r["failures"] and not r["errors"] and en["status"] == "OK" and 4.7 < en["limits"][0]["iv"][1] < 5.3,
      "synthetic divider-fed EN (200 k / 100 k from 15.5 V) PASSES", (en["status"], en["limits"], r["errors"]))
r = synth(nets, decl, resistors={"R1": "10kohm", "R2": "100kohm"})
check(keys(r) == ["U1.3"], "the same divider with 10 k on top (14 V at EN) FAILS", keys(r))
# the tap's own tolerance matters: 1 % resistors bound the divider outward
r = synth(nets, decl, resistors={"R1": "200kohm", "R2": "100kohm"})
iv = [x for x in r["rows"] if x["pin"] == "3"][0]["limits"][0]["iv"]
check(abs(iv[1] - 15.5 * 101 / (198 + 101)) < 1e-3, "divider upper bound uses R2+1 % over R1-1 % + R2+1 %", iv)
# a stale registry (a resistor that is not on the net) is an error, not a pass
r = synth(nets, decl, resistors={"R1": "200kohm", "R2": "100kohm", "R9": "10kohm"})
decl_bad = copy.deepcopy(decl)
decl_bad["en"]["r_top"] = ["R9"]
r = synth(nets, decl_bad, resistors={"R1": "200kohm", "R2": "100kohm", "R9": "10kohm"})
check(any("R9" in e for e in r["errors"]), "a divider whose resistor is not in the netlist is a registry ERROR", r["errors"])
# ---- 3. a pin referenced to a different ground is transformed into that part's frame
nets = {"g2": [("U1", "2")], "vin": [("U1", "1")], "en": [("U1", "3")], "out": [("U1", "5")], "nc": [("U1", "4")]}
base = {"g1": GND, "g2": rail("g1", 10.0, 10.0), "vin": rail("g1", 20.0, 20.0), "en": rail("g1", 12.0, 12.0),
        "out": rail("g1", 14.95, 15.05)}
r = synth(nets, base)
rows = {x["pin"]: x for x in r["rows"] if x["part"] == "U1"}
check(not r["failures"] and abs(rows["3"]["limits"][0]["iv"][1] - 2.0) < 1e-9 and abs(rows["1"]["limits"][0]["iv"][1] - 10.0) < 1e-9,
      "EN at 12 V against a part whose GND sits at 10 V reads 2 V (passes); IN reads 10 V", [x["limits"] for x in rows.values() if "limits" in x])
base2 = copy.deepcopy(base)
base2["g2"] = rail("g1", -10.0, -10.0)
r = synth(nets, base2)
check(keys(r) == ["U1.1", "U1.3"] or "U1.3" in keys(r), "the same nets with GND at -10 V put EN at 22 V: FAIL", keys(r))
# two different frames with no declared link: WARN-class FRAME, not a pass, not a FAIL
nets_f = {"g1": [("U1", "2")], "vin": [("U1", "1")], "en": [("U1", "3")], "out": [("U1", "5")], "nc": [("U1", "4")]}
fr = {"g1": GND, "vin": {"kind": "root", "cite": "synthetic", "derive": "a second, unlinked frame"}, "en": rail("g1", 0, 3), "out": rail("g1", 4.95, 5.05)}
r = synth(nets_f, fr)
check(not r["failures"] and any(x["status"] == "FRAME" for x in r["undeclared"]), "a pin net in an unlinked frame is reported FRAME (never silently OK)",
      [(x["pin"], x["status"]) for x in r["rows"]])
# ---- common-ancestor arithmetic: a supply and the rail it sits on do not widen each other
decl_c = {"leg": GND, "neg": rail("leg", -2.1, -1.9), "pos": rail("neg", 16.5, 17.5)}
m = g.NetModel({"nets": decl_c}, {}, {})
d = m.diff("pos", "neg")
check(d == (16.5, 17.5), "diff(pos, neg) is the declared span, not widened by neg's own spread", d)
d = m.diff("pos", "leg")
check(abs(d[0] - 14.4) < 1e-9 and abs(d[1] - 15.6) < 1e-9, "diff(pos, leg) adds the chain", d)
# a logic output measured against its own supply reads [-supply, 0], not a spread
decl_l = {"g": GND, "v": rail("g", 3.135, 3.465), "o": {"kind": "logic", "ref": "g", "supply": "v", "sources": [], "cite": "s", "derive": "d"}}
m = g.NetModel({"nets": decl_l}, {}, {})
check(m.diff("o", "v") == (-3.465, 0.0) and m.diff("o", "g") == (0.0, 3.465), "a logic net is exact against its supply and its ground", (m.diff("o", "v"), m.diff("o", "g")))
# ---- 4. a missing citation FAILS
reg = copy.deepcopy({"resistor_tolerance": {"_default": {"tol": 0.01}}, "nets": decl, "parts": {"TPS70950DBVR": LDO}})
del reg["parts"]["TPS70950DBVR"]["functions"]["EN"]["limits"][0]["quote"]
r = g.check(UNIT, reg, netlist({"gnd": [("U1", "2")], "vin": [("U1", "1"), ("U1", "3")], "out": [("U1", "5")], "nc": [("U1", "4")]}),
            {"U1": "TPS70950DBVR"}, {})
check(any("UNCITED limit" in e and "EN" in e for e in r["errors"]), "a limit with no quote is an UNCITED error", r["errors"])
reg = copy.deepcopy({"resistor_tolerance": {"_default": {"tol": 0.01}}, "nets": decl, "parts": {"TPS70950DBVR": LDO}})
reg["parts"]["TPS70950DBVR"]["functions"]["IN"]["limits"][0]["page"] = 0
r = g.check(UNIT, reg, netlist({"gnd": [("U1", "2")], "vin": [("U1", "1"), ("U1", "3")], "out": [("U1", "5")], "nc": [("U1", "4")]}),
            {"U1": "TPS70950DBVR"}, {})
check(any("UNCITED limit" in e and " IN " in e for e in r["errors"]), "a limit with no page is an UNCITED error", r["errors"])
reg = copy.deepcopy({"resistor_tolerance": {"_default": {"tol": 0.01}}, "nets": copy.deepcopy(decl), "parts": {"TPS70950DBVR": LDO}})
reg["nets"]["vin"]["cite"] = ""
r = g.check(UNIT, reg, netlist({"gnd": [("U1", "2")], "vin": [("U1", "1"), ("U1", "3")], "out": [("U1", "5")], "nc": [("U1", "4")]}),
            {"U1": "TPS70950DBVR"}, {})
check(any("UNCITED net vin" in e for e in r["errors"]), "a net range with no citation is an UNCITED error", r["errors"])
# ---- undeclared: WARN class, counted; --fail-undeclared turns it into a failure
nets_u = {"gnd": [("U1", "2")], "vin": [("U1", "1")], "en": [("U1", "3")], "out": [("U1", "5")], "nc": [("U1", "4")]}
decl_u = {"gnd": GND, "vin": rail("gnd", 14.4, 15.5), "out": rail("gnd", 4.95, 5.05)}
r = synth(nets_u, decl_u)
check(not r["failures"] and any(x["pin"] == "3" for x in r["undeclared"]) and r["coverage"]["undeclared"] == 1,
      "an undeclared net on an IC pin is reported, counted and not a FAIL by default", r["coverage"])
r2 = g.check(UNIT, {"resistor_tolerance": {"_default": {"tol": 0.01}}, "nets": decl_u, "parts": {"TPS70950DBVR": LDO}}, netlist(nets_u),
             {"U1": "TPS70950DBVR"}, {}, fail_undeclared=True)
check(keys(r2) == ["U1.3"], "--fail-undeclared makes it a FAIL", keys(r2))
# ---- logic sources are checked against the part registry
dl = {"gnd": GND, "vin": rail("gnd", 14.4, 15.5), "out": {"kind": "logic", "ref": "gnd", "supply": "vin", "sources": ["U1.5"], "cite": "s", "derive": "d"}}
r = synth({"gnd": [("U1", "2")], "vin": [("U1", "1")], "out": [("U1", "5")], "en": [("U1", "3")], "nc": [("U1", "4")]}, dl)
check(any("not an output" in e for e in r["errors"]), "a logic net whose source pin is not an `out` function is an ERROR", r["errors"])

# ---- 5. the real tree
root = UNIT
mpn_of, val = g.load_bom(root / "native-21/frozen/default.csv", root / "native-21/frozen/resolved-components.json")
text = (root / "native-21/frozen/default.net").read_text()
real = g.check(root, REAL, text, mpn_of, val)
check(not real["errors"], "real tree: no registry errors (topology, citations, sources all consistent)", real["errors"][:5])
# stage 48 (c48-ldo-en-ref-watch): the four EN pins sit on 100 k / 27 k dividers, so the real tree has no failure at all and
# the expected list is empty (the gate hard-gates from s48 on)
check(keys(real) == [], "real tree (stage 48) has no pin over its absolute maximum", keys(real))
exp_file = json.loads((HERE / "pin_absmax_expected.json").read_text())["expected"]
check(exp_file == {}, "pin_absmax_expected.json is empty (stage 48 closed U3.3 / U37.3 / U38.3 / U39.3)", sorted(exp_file))
real_e = g.check(root, REAL, text, mpn_of, val, expect=exp_file)
check(not real_e["new_failures"] and not real_e["stale_expected"], "with the expect-fail file there is no NEW failure and no stale entry")
en = {f"{x['part']}.{x['pin']}": x for x in real["rows"] if f"{x['part']}.{x['pin']}" in ("U3.3", "U37.3", "U38.3", "U39.3")}
check(len(en) == 4 and all(x["status"] == "OK" and x["limits"][0]["iv"][1] < 6.5 for x in en.values()),
      "the four divider-fed EN pins read inside 0 .. 6.5 V (recommended) against their GND", {k: x["limits"] for k, x in en.items()})
# EN rewired back onto IN, one LDO at a time: exactly that pin FAILS (the stage-48 regression control)
for ref, inn in (("U3", "v15_ls"), ("U37", "v15_ls"), ("U38", "p_ha"), ("U39", "p_hb")):
    node = f'      (node (ref "{ref}") (pin "3") (pintype "stereo"))\n'
    t2 = text.replace(node, "")
    head = f'(name "{inn}")\n'
    i = t2.index(head) + len(head)
    t2 = t2[:i] + node + t2[i:]
    r = g.check(root, REAL, t2, mpn_of, val)
    check(keys(r) == [f"{ref}.3"], f"{ref} EN back on IN ({inn}) FAILS on {ref}.3 only", keys(r))
# a listed entry that no longer fails is stale (what --fail-stale reports)
r = g.check(root, REAL, text, mpn_of, val, expect={"U3.3": "S19"})
check(r["stale_expected"] == ["U3.3"], "an expected entry that no longer fails is reported stale", r["stale_expected"])
extra = copy.deepcopy(REAL)
extra["parts"]["TLV3201AIDBVR"]["functions"]["VCC"]["limits"][0]["max"] = 4.0     # an invented tighter limit: hot5 (5.11 V) now fails
r = g.check(root, extra, text, mpn_of, val, expect=exp_file)
check(any(x["mpn"] == "TLV3201AIDBVR" for x in r["new_failures"]), "an injected tighter limit surfaces as a NEW failure")
reg_e = copy.deepcopy(REAL)
del reg_e["nets"]["hot5"]
r = g.check(root, reg_e, text, mpn_of, val, expect=exp_file)
check(r["coverage"]["undeclared"] > real["coverage"]["undeclared"], "removing a net declaration lowers coverage (the pins on it become UNDECLARED)")
# the vsense divider: the bus rating is where the AMC1311 sees 2.4 V, not 287 V
row = [x for x in real["rows"] if x["part"] == "U4" and x["pin"] == "2"][0]
check(row["status"] == "WARN" and 2.40 < row["limits"][0]["iv"][1] < 2.45, "real U4.IN is WARN (2.43 V at the OVP band top against VFSR 2 V, clipping 2.516 V)", (row["status"], row["limits"][0]["iv"]))
# fault envelope: PS2's OVP clamp (32.4 V) is above the R24C2T25 VIN abs max (32 V)
fw = [x for x in real["warnings"] if x["status"] == "WARN-FAULT"]
check(sorted(f"{x['part']}.{x['pin']}" for x in fw) == ["U41.6", "U41.7", "U42.6", "U42.7"], "real tree: only the R24C2T25 VIN pins exceed abs max under the PS2 OVP clamp envelope",
      [f"{x['part']}.{x['pin']}" for x in fw])

# ---- 6. rail registry vs the committed S16 rail model (rerunnable evidence for the rail figures)
S16 = UNIT / "validation-results/11-candidates/s16-monitor-2026-10-15/scripts"
sys.dont_write_bytecode = True
sys.path.insert(0, str(S16))
try:
    import model as m16
except Exception as e:                                                        # pragma: no cover
    m16 = None
    check(False, "S16 model importable", e)
if m16:
    ls, hs = m16.ls_span()["wc"], m16.hs_span(100.0)["wc"]
    nl, nh = m16.neg_rail("LS", 100.0)["wc"], m16.neg_rail("HS", 100.0)["wc"]
    N = REAL["nets"]
    enc = lambda net, lo, hi: N[net]["lo"] <= lo + 1e-12 and N[net]["hi"] >= hi - 1e-12 and (lo - N[net]["lo"]) < 2e-4 and (N[net]["hi"] - hi) < 2e-4
    check(enc("v15_ls", *ls), "v15_ls range encloses (and is within 0.2 mV of) S16 ls_span()", (N["v15_ls"], ls))
    check(enc("n_ls", -nl[1], -nl[0]), "n_ls range encloses S16 neg_rail('LS', 100 K)", (N["n_ls"], nl))
    check(enc("n_ha", -nh[1], -nh[0]) and enc("n_hb", -nh[1], -nh[0]), "n_ha / n_hb range encloses S16 neg_rail('HS', 100 K)", (N["n_ha"], nh))
    check(enc("p_ha", *hs) and enc("p_hb", *hs), "p_ha / p_hb range encloses S16 hs_span(100 K)", (N["p_ha"], hs))

# ---- 7. every quote sits on its cited page (needs the downloaded PDFs; skipped when absent)
dl = os.environ.get("PIN_ABSMAX_DL") or "/Users/bennet/Desktop/temper/worktrees/runs-native21/pin-absmax-dl"
if (Path(dl) / "pdf").is_dir():
    errs = g.verify_datasheets(REAL, dl)
    check(not errs, f"all datasheet quotes sit on their cited pages ({sum(len(f.get('limits', [])) + len(f.get('rec', [])) for p in REAL['parts'].values() for f in p['functions'].values())} rows)", errs[:5])
    bad = copy.deepcopy(REAL)
    bad["parts"]["TPS70950DBVR"]["functions"]["EN"]["limits"][0]["page"] = 5
    errs = g.verify_datasheets(bad, dl)
    check(any("TPS70950DBVR EN" in e for e in errs), "a quote moved to the wrong page is caught by --verify-datasheets")
    bad = copy.deepcopy(REAL)
    bad["parts"]["TPS70950DBVR"]["functions"]["EN"]["limits"][0]["max"] = 9
    errs = g.verify_datasheets(bad, dl)
    check(any("max 9" in e for e in errs), "a limit whose number is not in its quote is caught by --verify-datasheets")
else:
    print("skip datasheet-quote checks (no pdf dir at %s)" % dl)

print("\n%s" % ("all controls passed" if not fails else f"{fails} control(s) FAILED"))
sys.exit(1 if fails else 0)
