#!/usr/bin/env python3
"""Controls for bom_pricing.py (OPEN-ITEMS C8).

    python3 -I native-21/layout/gates/test_bom_pricing.py

Synthetic cases (no repo data) check the ladder, the tiers and the artefact rules; real-data cases check the RECOM
R24C2T25/R-R row, the s44 -> s45 delta against 11-candidates/c45-s16-monitor/results/cost-s44-s45.json (cost45.py's
like-for-like JLC ladders), that no line is estimated while a read exists, and byte-identical output on two runs.
PS_ROOT (env) overrides the unit root for a copy of this file kept outside the repo.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("bom_pricing", HERE / "bom_pricing.py")
bp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bp)

PS = Path(os.environ.get("PS_ROOT") or bp.UNIT)
VR = PS / "validation-results"
SRC = VR / "08-manufacturing-package/native-21/sourcing"
SNAP = SRC / "study-2026-10-15/snapshot"
# the s45 BOM as frozen in the sourcing study (the live fab BOM moved on at stage 46: TL431BQ / LM2901B, stage 47: LM4050)
BOM45 = SNAP / "s45/bom-jlcpcb.s45.csv"
BOM_LIVE = VR / "08-manufacturing-package/native-21/fab/bom-jlcpcb.csv"
BOM44 = SNAP / "s44/bom-jlcpcb.s44.csv"
fails = 0


def check(name, ok, detail=""):
    global fails
    fails += not ok
    print(("ok   " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))


def synth(jlc=None, octo=None, dk=None, survey=None):
    R = bp.Reads()
    R.raw = Path("/nonexistent")
    R.jlc = jlc or {}
    R.octo = octo or {}
    R.dk = dk or {}
    R.dk_early = {}
    R.survey = survey or {}
    return R


def jrec(mpn, ladder, stock, lib="expand", code="C1"):
    return {mpn: {"mpn": mpn, "lcsc_code": code, "jlc_found": True, "jlc_library": lib, "jlc_stock": stock,
                  "jlc_ladder": ladder, "fetched_utc": "2026-10-15T00:00:00Z", "url": "u"}}


def srow(mpn, u5, u500, src, est="no", stock=""):
    return {mpn: {"mpn": mpn, "check_date": "2026-10-13", "_file": "S.csv", "price_source": src, "price_is_estimate": est,
                  "unit_usd_at_5boards": str(u5), "unit_usd_at_500boards": str(u500), "digikey_stock": stock,
                  "jlc_stock_per_bom(date)": ""}}


# ---- ladder at the true lot quantity
lad = [(1, 0.014), (500, 0.0106), (1500, 0.0091), (4000, 0.0076), (24000, 0.0071), (48000, 0.0068)]
check("ladder: 25,500 parts takes the 24,000 break", bp.ladder_at(lad, 25500) == (0.0071, False))
check("ladder: 23,999 parts takes the 4,000 break", bp.ladder_at(lad, 23999) == (0.0076, False))
check("ladder: need below the first break takes it and says so", bp.ladder_at([(10, 1.0), (100, 0.5)], 5) == (1.0, True))
r = bp.price_line("X", 51, "C1", synth(jrec("X", lad, 10**8)), 500)
check("price_line: JLC in stock, lot 25,500 -> P1 at the 24,000 break", r["tier"] == "P1" and r["unit"] == 0.0071 and abs(r["line_usd"] - 0.3621) < 1e-9, r)

# ---- tiers
oct_ = {"X": {"url": "o", "offers": [{"seller": "Mouser", "authorized": True, "broker": False, "stock": 5000, "moq": 1,
                                       "usd_ladder": [[1, 2.0], [1000, 1.5]], "updated": "2026-10-14"},
                                      {"seller": "Shady", "authorized": False, "broker": False, "stock": 10**6, "moq": 1,
                                       "usd_ladder": [[1, 0.01]], "updated": "2026-10-14"}]}}
r = bp.price_line("X", 2, "C1", synth(jrec("X", [(1, 1.0)], 3), oct_), 500)
check("tier P2: JLC short (3 < 1000), authorised Mouser holds 5,000 -> 1.5, broker/unauthorised offer ignored",
      r["tier"] == "P2" and r["unit"] == 1.5, r)
r = bp.price_line("X", 2, "C1", synth(jrec("X", [(1, 1.0)], 5000), oct_), 500)
check("tier P1 beats a cheaper-or-dearer authorised offer when JLC holds the lot", r["tier"] == "P1" and r["unit"] == 1.0, r)
r = bp.price_line("X", 2, "C1", synth(jrec("X", [(1, 1.0)], 0), {"X": {"url": "o", "offers": []}}), 500)
check("tier P4: listed_no_stock alone is used last and flagged", r["tier"] == "P4" and "jlc_listed_no_stock_only" in r["flags"], r)

# ---- artefact rules
check("A3: 0.0204 against 7.37 is rejected", bp.artefact_reasons({"kind": "jlc", "listed_no_stock": True, "ladder": [(1, 1)]}, 0.0204, [7.37]) != [])
check("A3: exactly 10 % of the median is not rejected", bp.artefact_reasons({"kind": "auth", "ladder": [(1, 1)]}, 0.1, [1.0]) == [])
check("A3: no other read, no rejection", bp.artefact_reasons({"kind": "jlc", "ladder": [(1, 1)]}, 0.0204, []) == [])
check("A1: a zero price is rejected", bp.artefact_reasons({"kind": "auth", "ladder": [(1, 0)]}, 0.0, []) != [])
check("A2: listed_no_stock with no ladder is rejected", bp.artefact_reasons({"kind": "jlc", "listed_no_stock": True, "ladder": []}, None, []) != [])
sv = srow("X", 7.954, 7.37148, "DK", stock="1185")
r = bp.price_line("X", 2, "", synth(jrec("X", [(1, 0.0397), (500, 0.0204)], 0), None, None, sv), 500)
check("synthetic RECOM: the $0.0204 row is rejected, DK $7.37 is priced", r["unit"] == 7.37148 and r["tier"] == "P3"
      and any(c["artefact"] for c in r["candidates"] if c["kind"] == "jlc"), r)

# ---- estimates only where no read exists
est = srow("X", 0.05, 0.02, "ESTIMATE (class default, not fetched)", est="yes")
r = bp.price_line("X", 3, "", synth(survey=est), 500)
check("no read, estimate survey row -> P5, flagged", r["tier"] == "P5" and r["unit"] == 0.02 and "estimate" in r["flags"], r)
r = bp.price_line("X", 3, "C1", synth(jrec("X", [(1, 0.03)], 10**6), survey=est), 500)
check("a JLC read beats the estimate", r["tier"] == "P1" and r["unit"] == 0.03, r)
r = bp.price_line("X", 3, "", synth(), 500)
check("no read, no estimate -> unpriced", r["tier"] == "none" and r["unit"] is None, r)
eq = srow("X", 11.43, 11.43, "SET EQUAL to the -100ED (no quote)")
r = bp.price_line("X", 1, "", synth(survey=eq), 500)
check("a SET EQUAL proxy is not a read", r["tier"] == "P5", r)

# ---- real data
R = bp.load_reads(SRC)
P45 = bp.price_bom(BOM45, R)
P44 = bp.price_bom(BOM44, R)
L45 = {l["mpn"]: l for l in P45["lines"]}
recom = L45["R24C2T25/R-R"]
check("RECOM R24C2T25/R-R (s45): JLC $0.0204 / $0.0397 rejected by A3 at 5 and 500 boards",
      all(any(a.startswith("A3") for c in recom[f"n{n}"]["candidates"] if c["kind"] == "jlc" for a in c["artefact"]) for n in (5, 500)))
check("RECOM R24C2T25/R-R priced from DigiKey $7.954 / $7.37148, not $0.02",
      recom["n5"]["unit"] == 7.954 and recom["n500"]["unit"] == 7.37148, (recom["n5"]["unit"], recom["n500"]["unit"]))
check("TL431B is $0.0467 and LM4040A $1.2636 at 500 boards (JLC 2026-10-15 ladders)",
      L45["TL431BIDBZR"]["n500"]["unit"] == 0.0467 and L45["LM4040A25IDBZR"]["n500"]["unit"] == 1.2636)
ref = json.load(open(VR / "11-candidates/c45-s16-monitor/results/cost-s44-s45.json"))
d500 = P45["totals"]["parts_usd_at_500"] - P44["totals"]["parts_usd_at_500"]
check(f"s44 -> s45 delta at 500 boards {d500:+.4f} matches cost45.py's JLC-basis {ref['jlc_delta_usd_per_board']:+.4f} within $0.01",
      abs(d500 - ref["jlc_delta_usd_per_board"]) < 0.01)
A = {l["mpn"]: l for l in P44["lines"]}
worst = 0.0
for row in ref["rows"]:
    m = row["mpn"]
    y = L45[m]["n500"]["unit"] * L45[m]["qty"] if m in L45 else 0.0
    x = A[m]["n500"]["unit"] * A[m]["qty"] if m in A else 0.0
    worst = max(worst, abs((y - x) - row["jlc_delta"]))
check(f"every changed line matches cost45.py's per-line JLC delta (worst {worst:.5f})", worst < 0.005)
# estimates appear only where no read exists
bad = []
for P in (P44, P45):
    for l in P["lines"]:
        for n in (5, 500):
            x = l[f"n{n}"]
            has_read = any(c["unit"] and not c["artefact"] and c["kind"] in ("jlc", "auth") or
                           (c["kind"] == "survey" and c["survey_class"] in ("dist", "jlc") and c["unit"])
                           for c in x["candidates"])
            if x["tier"] in ("P5", "none") and has_read:
                bad.append((l["mpn"], n))
check("no line is estimated or unpriced while a read exists (s44, s45)", not bad, bad)
f45 = bp.card_fields(P45)
check("s45: price_estimated_lines and price_unpriced_lines match the P5 / none tiers",
      f45["price_estimated_lines"] == sorted({l["mpn"] for l in P45["lines"] if l["n5"]["tier"] == "P5" or l["n500"]["tier"] == "P5"})
      and f45["price_unpriced_lines"] == [], (f45["price_estimated_lines"], f45["price_unpriced_lines"]))

# ---- determinism
j1 = json.dumps(bp.price_bom(BOM45, bp.load_reads(SRC)), sort_keys=True)
j2 = json.dumps(bp.price_bom(BOM45, bp.load_reads(SRC)), sort_keys=True)
check("two in-process runs are byte-identical", j1 == j2)
with tempfile.TemporaryDirectory() as td:
    outs = []
    for i in (1, 2):
        o = Path(td) / f"o{i}.json"
        subprocess.run([sys.executable, "-I", str(HERE / "bom_pricing.py"), str(BOM45), "--sourcing", str(SRC), "--json", str(o)],
                       check=True, capture_output=True)
        outs.append(o.read_bytes())
    check("two CLI runs (python3 -I) write byte-identical JSON", outs[0] == outs[1] and len(outs[0]) > 1000)

    # ---- scorecard --compare: bases are never mixed silently (only when the patched scorecard.py sits beside this file)
    sc = HERE / "scorecard.py"
    if sc.exists() and "_parts_key" in sc.read_text():
        def card(path, cost):
            Path(path).write_text(json.dumps({"tag": path.stem, "gates": {}, "performance": {}, "cost": cost}))
        base = {"bom_lines": 94, "parts_usd_at_500": 201.6}
        new = dict(base, parts_usd_at_500=190.0, parts_usd_at_500_v2=170.0, price_basis=bp.BASIS)
        cn, co, cn2 = Path(td) / "new.json", Path(td) / "old.json", Path(td) / "new2.json"
        card(cn, new)
        card(co, base)
        card(cn2, dict(new, parts_usd_at_500_v2=171.0))
        r = subprocess.run([sys.executable, "-I", str(sc), "--card", str(cn), "--compare", str(co)], capture_output=True, text=True)
        check("compare: new-basis card vs old-basis benchmark says so and uses the legacy key",
              "NOTE: price basis differs" in r.stdout and "cheaper ['parts_usd_at_500']" in r.stdout, r.stdout)
        r = subprocess.run([sys.executable, "-I", str(sc), "--card", str(cn), "--compare", str(co), "--strict-basis"], capture_output=True, text=True)
        check("compare --strict-basis: refuses (REJECT, exit 1)", r.returncode == 1 and "REJECT" in r.stdout and "not comparable" in r.stdout, r.stdout)
        r = subprocess.run([sys.executable, "-I", str(sc), "--card", str(cn), "--compare", str(cn2)], capture_output=True, text=True)
        check("compare: two v2 cards compare on parts_usd_at_500_v2", "parts_usd_at_500_v2" in r.stdout and "NOTE" not in r.stdout, r.stdout)

# stage 47: U5 LM4050AEM3-2.5/NOPB (C2156518), 50 at JLC: JLC stock at 5 boards; nobody holds 500 (P3, short) on the dated reads
LL = {l["mpn"]: l for l in bp.price_bom(BOM_LIVE, R)["lines"]}
u5 = LL.get("LM4050AEM3-2.5/NOPB")
check("LM4050AEM3-2.5 (s47): P1 $5.1472 at 5 boards, P3 $3.4228 (short) at 500 (JLC 2026-10-15 ladder, 50 in stock)",
      u5 is not None and u5["n5"]["tier"] == "P1" and u5["n5"]["unit"] == 5.1472 and u5["n500"]["tier"] == "P3"
      and u5["n500"]["unit"] == 3.4228, u5 and (u5["n5"], u5["n500"]))

print("PASS" if not fails else f"FAIL ({fails})")
raise SystemExit(1 if fails else 0)
