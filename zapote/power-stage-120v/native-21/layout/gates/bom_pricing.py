#!/usr/bin/env python3
"""BOM pricing from real price reads (OPEN-ITEMS C8). Called by scorecard.py; also runnable on its own.

    python3 -I native-21/layout/gates/bom_pricing.py BOM.csv [--json OUT.json] [--lines]

Why: the legacy card sums STOCK-2026-10-13*.csv, where 58 of 94 lines hold a class-default ESTIMATE (an 0603 thin-film
resistor $0.008, TL431A $0.40 against JLC's $0.049, LM4040A $0.40 against $1.26). A BOM-only swap then scores the
difference between a guess and a read. This module prices every line from the best dated read instead and takes an
estimate only when no read exists at all.

Reads (all committed, all offline, all dated; nothing is fetched here):
  JLC    sourcing/study-2026-10-15/snapshot/jlc-2026-10-15.json, else scripts/jlc-raw/detail_<LCSC code>.json for a line
         the snapshot lacks (a part added after the snapshot, e.g. the s45 resistors). Price ladder, stock, library.
  AUTH   snapshot/digikey-2026-10-15.json (DigiKey page read) and snapshot/octopart-2026-10-15.json (authorised,
         non-broker offers: DigiKey, Mouser, Newark, Future, ...). Price ladder, stock, MOQ. Brokers are never priced.
  SURVEY STOCK-2026-10-13*.csv rows that are reads (DK / DigiKey / JLC / LCSC). Rows that are class-default ESTIMATES,
         "SET EQUAL" proxies or ratio-derived prices are not reads. Two points only: unit price at 5 and 500 boards.

Preference order, per line and per board count N (lot need = qty_per_board x N parts). First tier that has a price wins;
inside a tier the lowest non-artefact price wins, ties broken by source name.
  P1  JLC stock       JLC library part (basic / extended) whose JLC stock >= need: the JLC ladder price at need.
  P2  authorised      an authorised distributor offer holding >= need with MOQ <= need (JLC Global Sourcing route):
                      its ladder price at need.
  P3  nobody holds    no source holds the need; priced as an order / split buy from the read whose stock covers the
                      largest share of the lot (a survey read with no stock count covers 0), then the lowest price,
                      over: authorised ladders (stock ignored), survey reads, and the ladder of a JLC library part
                      whose stock is short. The bulk of the lot is bought where the stock is. Flag: short (no 2026-10-15 read shows a holder).
  P4  JLC listed_no_stock   the JLC page lists the part with stock 0: its ladder is a catalogue price, not an offer. Used
                      only when P1-P3 are empty, and only if it passes the artefact rules.
  P5  estimate        the class-default estimate (or proxy) from the survey row, listed in price_estimated_lines.
      none            no survey row either: the line is unpriced (unpriced_lines).

Artefact rules (a price failing any is dropped from P1-P4 and listed in price_artefact_lines):
  A1  zero or negative price. (A source with no price at all is simply not a candidate.)
  A2  a JLC listed_no_stock row with no ladder.
  A3  a price below 10 % of the median of the other priced reads for the same line and quantity (a read is a JLC,
      authorised or survey-read price; estimates never count). Needs at least one other read. This catches the RECOM
      R24C2T25/R-R row: JLC lists $0.0204 (listed_no_stock) against DigiKey $7.37.
  A4  a JLC listed_no_stock ladder is never a P1 price (JLC cannot sell what it does not hold).

Ladder price at the true lot quantity: the price of the largest break <= need. If need is below the first break the
first-break price is used and the line is flagged below_first_break (MOQ above need; the excess is bought but not
priced). Per-board line cost = unit price x qty_per_board.
"""
import csv
import glob
import json
import statistics
from pathlib import Path

BASIS = "bom_pricing-v1"
ARTEFACT_FRACTION = 0.10
BOARDS = (5, 500)
UNIT = Path(__file__).resolve().parents[3]            # zapote/power-stage-120v
SOURCING = UNIT / "validation-results/08-manufacturing-package/native-21/sourcing"
LIBS = {"base": "basic", "expand": "extended"}


# ---------------------------------------------------------------- reads
def _n(x):
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def survey_class(r):
    """read class of a STOCK-*.csv row: dist | jlc | estimate | derived | other (only dist / jlc are reads)."""
    ps = r.get("price_source", "").strip()
    up = ps.upper()
    if r.get("price_is_estimate", "").strip().lower().startswith("yes") or up.startswith("ESTIMATE"):
        return "estimate"
    if up.startswith("SET EQUAL") or ("BENCHMARK" in up and "RATIO" in up):
        return "derived"
    if ps.startswith(("DK", "DigiKey")):
        return "dist"
    if ps.startswith(("JLC", "LCSC")):
        return "jlc"
    return "other"


class Reads:
    pass


def load_reads(sourcing=None):
    """Load every committed read once. `sourcing` = the sourcing/ folder (default: this unit's)."""
    S = Path(sourcing) if sourcing else SOURCING
    snap = S / "study-2026-10-15/snapshot"
    R = Reads()
    R.sourcing = S
    R.raw = S / "study-2026-10-15/scripts/jlc-raw"
    j = json.load(open(snap / "jlc-2026-10-15.json"))
    R.jlc = {}
    for rec in j["extra"] + j["bom"]:                   # bom rows win over alternates
        R.jlc[rec["mpn"]] = rec
    R.octo = json.load(open(snap / "octopart-2026-10-15.json"))
    dk = json.load(open(snap / "digikey-2026-10-15.json"))
    R.dk = {r["mpn"].replace(" ", ""): r for r in dk["records"]}
    R.dk_early = {k: v for k, v in dk.get("earlier_fetch_ok", {}).items() if not k.startswith("_")}
    R.survey = {}
    for p in sorted(glob.glob(str(S / "STOCK-2026-10-13*.csv"))):
        for r in csv.DictReader(open(p)):
            if not r["board"].startswith("power"):
                continue
            k = r["mpn"].strip()
            old = R.survey.get(k)
            if old is None or r["check_date"] >= old["check_date"]:     # newer check wins; a tie goes to the later file
                r["_file"] = Path(p).name
                R.survey[k] = r
    R.files = ["study-2026-10-15/snapshot/jlc-2026-10-15.json", "study-2026-10-15/snapshot/octopart-2026-10-15.json",
               "study-2026-10-15/snapshot/digikey-2026-10-15.json", "study-2026-10-15/scripts/jlc-raw/detail_*.json",
               "STOCK-2026-10-13*.csv"]
    return R


def _jlc_cand(R, mpn, code):
    rec = R.jlc.get(mpn)
    if rec and rec.get("jlc_found") and (not code or rec.get("lcsc_code") == code):
        lad, lib, stock, date, url = rec.get("jlc_ladder") or [], rec.get("jlc_library"), rec.get("jlc_stock") or 0, rec.get("fetched_utc"), rec.get("url")
    elif code and (R.raw / f"detail_{code}.json").exists():
        raw = json.load(open(R.raw / f"detail_{code}.json"))
        d = raw.get("data") or {}
        lad = [(p["startNumber"], p["productPrice"]) for p in d.get("prices") or []]
        lib, stock, date, url = d.get("componentLibraryType"), d.get("stockCount") or 0, raw.get("_fetched_utc"), f"https://jlcpcb.com/partdetail/{code}"
    elif rec and rec.get("jlc_found"):
        lad, lib, stock, date, url = rec.get("jlc_ladder") or [], rec.get("jlc_library"), rec.get("jlc_stock") or 0, rec.get("fetched_utc"), rec.get("url")
    else:
        return None
    lib = LIBS.get(lib)
    return {"kind": "jlc", "source": f"JLC part page {code or rec.get('lcsc_code')}", "date": date, "url": url, "stock": stock,
            "moq": None, "ladder": [(int(a), float(b)) for a, b in lad], "points": None, "library": lib,
            "listed_no_stock": lib is not None and stock == 0, "in_library": lib is not None}


def _auth_cands(R, mpn):
    out = []
    dk = R.dk.get(mpn.replace(" ", ""))
    early = R.dk_early.get(mpn)
    for x in sorted(R.octo.get(mpn, {"offers": []})["offers"], key=lambda o: (o["seller"], o.get("sku") or "")):
        if not x.get("authorized") or x.get("broker"):
            continue
        if x["seller"].startswith(("DigiKey", "Digi-Key")) and (dk or early):
            continue                                    # today's direct DigiKey page read replaces Octopart's DigiKey row
        out.append({"kind": "auth", "source": f"{x['seller']} via Octopart", "date": x.get("updated"), "url": R.octo[mpn].get("url"),
                    "stock": x.get("stock") or 0, "moq": x.get("moq") or 1, "ladder": [(int(a), float(b)) for a, b in x["usd_ladder"]],
                    "points": None})
    if dk:
        out.append({"kind": "auth", "source": "Digi-Key (page read)", "date": dk["t"], "url": dk.get("url"), "stock": dk["stock"],
                    "moq": 1, "ladder": [(int(a), float(b)) for a, b in dk["tiers"]], "points": None})
    elif early:
        out.append({"kind": "auth", "source": "Digi-Key (in-page read, two points)", "date": "2026-10-15 (06:4x Z)", "url": None,
                    "stock": early[0], "moq": 1, "ladder": [], "points": {5: early[2], 500: early[3]}})
    return out


def _lead_int(x):
    """leading integer of a survey stock cell ('7183 (486-3564-2-ND)' -> 7183); None when the cell is text."""
    import re
    m = re.match(r"\s*(\d[\d,]*)", str(x or ""))
    return int(m.group(1).replace(",", "")) if m else None


def _survey_cand(R, mpn):
    r = R.survey.get(mpn)
    if not r:
        return None
    cls = survey_class(r)
    stock = _lead_int(r.get("digikey_stock") if cls == "dist" else r.get("jlc_stock_per_bom(date)") if cls == "jlc" else None)
    return {"kind": "survey", "cls": cls, "source": f"{r['_file']}: {r['price_source'].strip()[:90]}",
            "date": r["check_date"], "url": None, "stock": stock, "moq": None, "ladder": [],
            "points": {5: _n(r["unit_usd_at_5boards"]), 500: _n(r["unit_usd_at_500boards"])}}


# ---------------------------------------------------------------- pricing
def ladder_at(ladder, need):
    """(price, below_first_break) at the largest break <= need; the first break if need is below it."""
    if not ladder:
        return None, False
    best, below = None, True
    for q, p in sorted(ladder):
        if need >= q:
            best, below = p, False
    if best is None:
        return sorted(ladder)[0][1], True
    return best, below


def price_at(c, boards, need):
    if c["points"] is not None:
        return c["points"].get(boards), False
    return ladder_at(c["ladder"], need)


def artefact_reasons(c, price, others):
    """Rules A1-A3 for one read: price at need, and the prices of the other reads at the same need."""
    why = []
    if c["kind"] == "jlc" and c.get("listed_no_stock") and not c["ladder"]:
        why.append("A2 listed_no_stock row with no ladder")
    if price is not None and price <= 0:
        why.append("A1 zero or negative price")
    elif price is not None and others:
        med = statistics.median(others)
        if price < ARTEFACT_FRACTION * med:
            why.append(f"A3 {price:g} is below {ARTEFACT_FRACTION:.0%} of the median {med:g} of the other reads")
    return why


def channel_of(c):
    """Price channel of a read: 'jlc' (JLC part-page ladder or a JLC survey read), 'digikey' (DigiKey page, Octopart DigiKey
    offer or a DK survey read), 'distributor' (any other authorised seller), 'estimate' (class default / derived)."""
    if c["kind"] == "jlc":
        return "jlc"
    if c["kind"] == "auth":
        return "digikey" if c["source"].startswith(("Digi-Key", "DigiKey")) else "distributor"
    return {"dist": "digikey", "jlc": "jlc"}.get(c.get("cls"), "estimate")


def price_line(mpn, qty, code, R, boards):
    """Price one BOM line for `boards` boards. Returns a dict with the chosen price, tier, source, date, flags and
    every candidate considered."""
    need = qty * boards
    cands = []
    j = _jlc_cand(R, mpn, code)
    if j:
        cands.append(j)
    cands += _auth_cands(R, mpn)
    sv = _survey_cand(R, mpn)
    if sv:
        cands.append(sv)
    for c in cands:
        c["price"], c["below_first"] = price_at(c, boards, need)
    reads = [c for c in cands if not (c["kind"] == "survey" and c["cls"] not in ("dist", "jlc"))]
    for c in cands:
        others = [o["price"] for o in reads if o is not c and o["price"] and o["price"] > 0]
        c["artefact"] = artefact_reasons(c, c["price"], others) if c in reads else []
    ok = [c for c in reads if not c["artefact"]]

    def pick(pool, tier):
        pool = [c for c in pool if c["price"]]
        if not pool:
            return None
        # P1 / P2 / P4 pools already agree on stock; in P3 the read whose stock covers most of the lot goes first
        c = min(pool, key=lambda c: (-round(min(c["stock"] or 0, need) / need, 6) if tier == "P3" else 0, c["price"], c["source"]))
        return c, tier

    got = None
    j_ok = next((c for c in ok if c["kind"] == "jlc"), None)
    if j_ok and j_ok["in_library"] and not j_ok["listed_no_stock"] and j_ok["stock"] >= need:
        got = pick([j_ok], "P1")
    if not got:
        got = pick([c for c in ok if c["kind"] == "auth" and (c["stock"] or 0) >= need and (c["moq"] or 1) <= need], "P2")
    if not got:
        got = pick([c for c in ok if c["kind"] in ("auth", "survey")
                    or (c["kind"] == "jlc" and c["in_library"] and not c["listed_no_stock"])], "P3")
    if not got:
        got = pick([c for c in ok if c["kind"] == "jlc" and c["listed_no_stock"]], "P4")
    flags = []
    if got:
        c, tier = got
        unit, source, date = c["price"], c["source"], c["date"]
        channel = channel_of(c)
        if tier == "P3":
            flags.append("short: no 2026-10-15 read shows a source holding the lot; priced from the best-covering read")
        if tier == "P4":
            flags.append("jlc_listed_no_stock_only")
        if c["below_first"]:
            flags.append("below_first_break (MOQ above need)")
        if c["kind"] == "auth" and (c["moq"] or 1) > need:
            flags.append(f"moq {c['moq']} above need")
        if c["kind"] == "survey":
            flags.append("survey read (2026-10-13/14), older than the 2026-10-15 snapshot"
                         + ("; its stock count covers the lot but was not re-read" if (c["stock"] or 0) >= need else ""))
    else:
        e = R.survey.get(mpn)
        unit = _n(e[("unit_usd_at_5boards" if boards == 5 else "unit_usd_at_500boards")]) if e else None
        if unit is not None:
            channel = "estimate"
            tier, source, date = "P5", f"ESTIMATE {e['_file']}: {e['price_source'].strip()[:90]}", e["check_date"]
            flags.append("estimate")
        else:
            channel = "none"
            tier, source, date = "none", "", ""
            flags.append("unpriced")
    # cheapest stock-holding read (JLC stock or authorised stock), for the sensitivity total only
    hold = [c["price"] for c in ok if c["price"] and (
        (c["kind"] == "jlc" and c["in_library"] and not c["listed_no_stock"] and c["stock"] >= need)
        or (c["kind"] == "auth" and (c["stock"] or 0) >= need and (c["moq"] or 1) <= need))]
    rec = {"boards": boards, "need": need, "unit": unit, "line_usd": None if unit is None else round(unit * qty, 6),
           "tier": tier, "source": source, "date": date, "flags": flags, "channel": channel,
           "channel_prices": _channel_prices(ok),
           "cheapest_stock_holding_unit": min(hold) if hold else None,
           "candidates": [{"source": c["source"], "kind": c["kind"], "date": c["date"], "stock": c["stock"], "moq": c["moq"],
                           "unit": c["price"], "artefact": c["artefact"],
                           "non_purchasable": bool(c.get("listed_no_stock")),
                           "survey_class": c.get("cls")} for c in cands]}
    return rec


def _channel_prices(ok):
    """Lowest non-artefact unit price per price channel (estimates excluded): lets a comparison re-price a line on a
    channel both cards have a read for. A JLC listing with stock 0 is a catalogue price, kept apart as 'jlc_no_stock'."""
    out = {}
    for c in ok:
        if not c["price"] or (c["kind"] == "survey" and c.get("cls") not in ("dist", "jlc")):
            continue
        no_stock = c.get("listed_no_stock") or (c["kind"] == "survey" and c.get("cls") == "jlc" and c["stock"] == 0)
        ch = "jlc_no_stock" if no_stock else channel_of(c)
        if ch not in out or c["price"] < out[ch]:
            out[ch] = c["price"]
    return out


def read_bom(path):
    rows = []
    for r in csv.DictReader(open(path)):
        r["_qty"] = len([d for d in r["Designator"].split(",") if d.strip()])
        rows.append(r)
    return rows


def price_bom(bom_path, R=None, boards=BOARDS):
    """Price every line of a BOM CSV (fab/bom-jlcpcb.csv layout). Returns {"lines": [...], "totals": {...}}."""
    R = R or load_reads()
    lines = []
    for i, r in enumerate(read_bom(bom_path), 1):
        mpn = r["Manufacturer Part Number"].strip()
        code = r.get("LCSC Part #", "").strip()
        rec = {"line": i, "designators": r["Designator"], "mpn": mpn, "lcsc": code, "qty": r["_qty"]}
        for n in boards:
            rec[f"n{n}"] = price_line(mpn, r["_qty"], code, R, n)
        lines.append(rec)
    return {"lines": lines, "totals": totals(lines, boards)}


def totals(lines, boards=BOARDS):
    t = {}
    for n in boards:
        key = f"n{n}"
        t[f"parts_usd_at_{n}"] = round(sum(l[key]["line_usd"] or 0.0 for l in lines), 4)
        t[f"parts_usd_at_{n}_cheapest_stock_holding"] = round(sum(
            (l[key]["cheapest_stock_holding_unit"] if l[key]["cheapest_stock_holding_unit"] is not None else (l[key]["unit"] or 0.0)) * l["qty"]
            for l in lines), 4)
        t[f"tiers_{n}"] = {k: sum(l[key]["tier"] == k for l in lines) for k in ("P1", "P2", "P3", "P4", "P5", "none")}
    return t


def card_fields(priced):
    """The cost keys scorecard.py adds. Legacy keys (parts_usd_at_5, parts_usd_at_500, unpriced_lines) keep their
    2026-10-13 stock-survey meaning; these are the new, versioned ones."""
    L, T = priced["lines"], priced["totals"]
    est = sorted({l["mpn"] for l in L for n in BOARDS if l[f"n{n}"]["tier"] == "P5"})
    unp = sorted({l["mpn"] for l in L for n in BOARDS if l[f"n{n}"]["tier"] == "none"})
    art = sorted({f"{l['mpn']}: {a}" for l in L for n in BOARDS for c in l[f"n{n}"]["candidates"] for a in c["artefact"]})
    return {
        "price_basis": BASIS,
        "parts_usd_at_5_v2": round(T["parts_usd_at_5"], 2),
        "parts_usd_at_500_v2": round(T["parts_usd_at_500"], 2),
        "price_estimated_lines": est,
        "price_unpriced_lines": unp,
        "price_artefact_lines": art,
        "price_short_lines_5": sorted(l["mpn"] for l in L if l["n5"]["tier"] == "P3"),
        "price_short_lines_500": sorted(l["mpn"] for l in L if l["n500"]["tier"] == "P3"),
        "price_tiers_5": T["tiers_5"],
        "price_tiers_500": T["tiers_500"],
        # per line (keyed by designators) channel + unit at the 500-board lot, for same-channel comparison (scorecard.compare)
        "price_lines_500": [{"designators": l["designators"], "mpn": l["mpn"], "qty": l["qty"], "tier": l["n500"]["tier"],
                             "channel": l["n500"]["channel"], "unit": l["n500"]["unit"],
                             "channel_prices": l["n500"]["channel_prices"]} for l in L],
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("bom")
    ap.add_argument("--json")
    ap.add_argument("--sourcing")
    ap.add_argument("--lines", action="store_true")
    a = ap.parse_args()
    P = price_bom(a.bom, load_reads(a.sourcing))
    out = {"basis": BASIS, "card_fields": card_fields(P), "totals": P["totals"], "lines": P["lines"]}
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"card_fields": out["card_fields"], "totals": out["totals"]}, indent=1, sort_keys=True))
    if a.lines:
        for l in P["lines"]:
            print(l["line"], l["mpn"], l["n5"]["tier"], l["n5"]["unit"], l["n500"]["tier"], l["n500"]["unit"])


if __name__ == "__main__":
    main()
