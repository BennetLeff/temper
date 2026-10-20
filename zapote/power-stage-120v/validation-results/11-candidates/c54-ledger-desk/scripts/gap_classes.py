#!/usr/bin/env python3
"""Classify every remaining gap in the datasheet ledger and name its closing test or answer (stdlib only).

    python3 -I validation-results/11-candidates/c54-ledger-desk/scripts/gap_classes.py

Classes: bench (a measurement closes it), certifier (an approval / abnormal-operation test or the certifier's
acceptance), owner (a decision, a maker question, a sourcing / library / interface record), B3-estimate (the local
temperature or a thermal number is the B3 body model, not a measurement), model-estimate (another model that is not
re-run or not a bound). Explicit prefixes in the gap text win; untagged legacy gaps are classified by the table below.
Writes results/gap-classes.md (and results/gap-classes.json).
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
LANE = HERE.parent
UNIT = HERE.parents[3]
LEDGER = UNIT / "native-21/verification/datasheet-ledger/ledger.json"

# untagged legacy gaps: (mpn, text prefix) -> (class, closing test / answer)
LEGACY = [
    ("IPW65R018CFD7", "Maximum-Qrr basis", "bench", "D-8 bench: R_on 39 / 68 / 100 ohm x Cgs 1 / 4.7 nF with repeated S4 edges; diode dv/dt <= 56 V/ns (80 %) at the measured Qrr."),
    ("IPW65R018CFD7", "Switching loss", "bench", "Double-pulse / S4 bench: switching loss, S4 / S5 dv/dt and die VDS measured on the board."),
    ("IPW65R018CFD7", "Tj at 28 A", "bench", "Record the S8 baseline Tj (case thermocouple + Rth) on the fitted sink; the 28 A / 50 kHz step stays closed until it passes 125 C (owner: K1 contingency sink only if it fails)."),
    ("IPW65R018CFD7", "F7 loop re-extraction", "model-estimate", "F7 FEM loop re-extraction on the board of record (FINDINGS #1); S3 closed F6 on the s51 matrices, so check whether F7 is now covered (possibly stale)."),
    ("TPS70950QDBVRQ1", "the U3 junction is the B3", "B3-estimate", None),
    ("TPS70950QDBVRQ1", "U37-U39 have no junction row", "B3-estimate", "Re-run temp_ratings with the TPS70950QDBVRQ1 line (U37-U39 local rows) so they can be cited; then the bench run as for every B3 row."),
    ("TPS70950QDBVRQ1", "U3's input cap C25", "owner", "Layout: move C25 to U3's IN pin at the next spin (7.4.1 p.19), or accept with the bench ripple / stability check of U3."),
    ("LM4050AEM3-2.5/NOPB", "the local temperature", "B3-estimate", None),
    ("LM4050AEM3-2.5/NOPB", "long-term drift", "owner", "Maker question / accept: TI gives only typical drift (120 ppm / 1000 h) and hysteresis; accept inside the band model's 0.5 % target or add a calibration step at commissioning."),
    ("RT0603BRD077K5L", "the local temperature", "B3-estimate", None),
    ("RT0603BRD0716KL", "the local temperature", "B3-estimate", None),
    ("TL431BQDBZR", "the local temperature", "B3-estimate", None),
    ("TL431BQDBZR", "the fault-case span", "certifier", "Abnormal-operation test: LS LDO pass short (V24_RAW up to the 32.4 V PS2 OVP clamp on the span) with the monitor fitted; record the outcome. The registry now carries the 32.4 V fault envelope, so a desk re-run of the span at 32.4 V can narrow it."),
    ("TL431BQDBZR", "Vref long-term", "owner", "Maker question (TI publishes no load-life drift) or accept inside the band analysis's 0.5 % margin."),
    ("RT0603BRD07750RL", "the fault-case span", "certifier", "As TL431BQDBZR: the LS-pass-short abnormal test, or a desk re-run of the span at the 32.4 V fault envelope."),
    ("RT0603BRD072K94L", "the fault-case span", "certifier", "As TL431BQDBZR."),
    ("RT0603BRD0790K9L", "the fault-case span", "certifier", "As TL431BQDBZR."),
    ("RT0603BRD07104KL", "the fault-case span", "certifier", "As TL431BQDBZR."),
    ("LM2901BIDR", "the local temperature", "B3-estimate", None),
    ("LM2901BIDR", "the fault-case span", "certifier", "As TL431BQDBZR."),
    ("LM2901BIDR", "fault states where src floats", "certifier", "Single-fault test (R77 / TLVH431 open) with the comparator output observed; the datasheet note 1 (6.8 p.8) argument is the desk basis."),
    ("CL32B106KBJNNNE", "s19b BP-04", "owner", "Accept (no rail states a minimum there and the P-N start-up bound holds) or fit a higher-voltage / larger case part; record the decision."),
    ("CL32B106KBJNNNE", "X7R ageing", "bench", "Measure C at the rail bias and 100 C after ageing (or take the maker's ageing curve) and re-run the BP-04 / start-up check."),
    ("25121WF680JT4E", "No single-pulse rating", "owner", "Maker question: UniRoyal single-pulse rating at < 1 us; or bench: gate-edge pulse test at 2x the stress."),
    ("GRM1885C1H472JA01D", "Pulse current", "owner", "Maker question / accept: Murata's ripple / pulse curve for the C0G part (dissipation negligible); no check expected to move."),
]

DEFAULTS = {
    "B3-estimate": "Bench thermal run: thermocouple / IR on the part at the release case (17.5 A ceiling, 18.375 A trip, still "
                   "air) with the bay temperature measured; compare with the B3 estimate (the S25 pre-lot thermal run "
                   "covers the gated rows).",
    "owner airflow": "Owner: keep the 17.5 A release ceiling (DECISIONS 56), or provide board-face airflow / a measured bay "
                     "that gives a passing B3 basis before raising it (b3-ratings/ENCLOSURE-REQUEST.md).",
}


def classify(mpn, g):
    t = g
    if t.startswith("[temp-ratings"):
        t = t.split("] ", 1)[1]
        if t.startswith("owner: airflow route"):
            return "owner", DEFAULTS["owner airflow"], "airflow route (c22 / c28)"
        if t.startswith("the local temperature") or t.startswith("the junction"):
            return "B3-estimate", DEFAULTS["B3-estimate"], "B3 body-model temperature"
    m = re.match(r"(bench|certifier|owner|B3-estimate|model-estimate|finding)\b", t)
    if m:
        cls = {"finding": "owner"}.get(m.group(1), m.group(1))
        sub = "finding (owner decision + bench)" if m.group(1) == "finding" else ""
        c = re.search(r"(Closing (?:test|answer)?[^:]*:\s*)(.*)", t)
        return cls, (c.group(2) if c else None), sub
    for lm, pre, cls, close in LEGACY:
        if lm == mpn and t.startswith(pre):
            return cls, close or DEFAULTS.get(cls), "untagged legacy gap"
    return "UNCLASSIFIED", None, ""


def main():
    L = json.loads(LEDGER.read_text())["entries"]
    rows, unc = [], []
    for mpn, e in L.items():
        for i, g in enumerate(e["gaps"]):
            cls, close, sub = classify(mpn, g)
            if cls == "UNCLASSIFIED":
                unc.append((mpn, g))
            rows.append({"mpn": mpn, "class_line": e["class"], "status": e["status"], "designators": e["designators"],
                         "i": i, "gap_class": cls, "sub": sub, "closing": close or "the gap text names the test / answer",
                         "gap": g})
    if unc:
        raise SystemExit("unclassified gaps:\n" + "\n".join(f"{m}: {g[:120]}" for m, g in unc))
    by = Counter(r["gap_class"] for r in rows)
    lines_by = defaultdict(set)
    for r in rows:
        lines_by[r["gap_class"]].add(r["mpn"])
    only_b3 = sorted(m for m, e in L.items() if e["gaps"] and all(classify(m, g)[0] == "B3-estimate" for g in e["gaps"])
                     and not any(c["ratio"] > c["max_ratio"] + 1e-9 for c in e["checks"]))
    out = ["# Gap classes: every remaining datasheet-ledger gap (generated by scripts/gap_classes.py; do not edit)", "",
           f"Ledger: {len(L)} lines, {Counter(e['status'] for e in L.values())}. Gaps: {len(rows)}.", "",
           "| class | gaps | lines | what closes it |", "|---|---|---|---|"]
    expl = {"bench": "a measurement on the board / part", "certifier": "an approval answer or abnormal-operation test",
            "owner": "a decision, maker question, sourcing / library / interface record, or the airflow route",
            "B3-estimate": "a measured temperature in place of the B3 body model",
            "model-estimate": "re-running / committing a model that is not a bound"}
    for c in ("bench", "certifier", "owner", "B3-estimate", "model-estimate"):
        out.append(f"| {c} | {by.get(c, 0)} | {len(lines_by[c])} | {expl[c]} |")
    out += ["", f"**Lines PARTIAL only because of the B3-estimate gap ({len(only_b3)}):** every electrical and temperature "
            "check passes and the only open item is that the local temperature is the B3 model, not a measurement. They "
            "become VERIFIED on the bench thermal run (no desk action can close them honestly): " + ", ".join(only_b3) + ".",
            ""]
    for c in ("bench", "certifier", "owner", "model-estimate", "B3-estimate"):
        rs = [r for r in rows if r["gap_class"] == c]
        out += [f"## {c} ({len(rs)})", "", "| line | refs | gap | closing test / answer |", "|---|---|---|---|"]
        for r in rs:
            g = r["gap"].replace("|", "/").replace("\n", " ")
            g = g if len(g) <= 420 else g[:417] + "..."
            refs = ",".join(r["designators"][:6]) + ("..." if len(r["designators"]) > 6 else "")
            sub = f" *({r['sub']})*" if r["sub"] else ""
            out.append(f"| {r['mpn']} | {refs} | {g}{sub} | {r['closing'].replace('|', '/')} |")
        out.append("")
    (LANE / "results/gap-classes.md").write_text("\n".join(out) + "\n")
    (LANE / "results/gap-classes.json").write_text(json.dumps({"counts": by, "only_b3": only_b3, "rows": rows}, indent=1) + "\n")
    print(dict(by), len(rows), "gaps;", len(only_b3), "lines B3-only")


if __name__ == "__main__":
    main()
