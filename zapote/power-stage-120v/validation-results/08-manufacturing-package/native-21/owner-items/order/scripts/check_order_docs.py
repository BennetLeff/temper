#!/usr/bin/env python3
"""The documents someone orders from must match the board of record. Read only; exit 1 on any mismatch.

    python3 -I owner-items/order/scripts/check_order_docs.py [--root native-21] [--selftest]

Truth: fab/FAB-NOTE.md (stage, board SHA, zip SHA, order remark), the zip itself, the BOM Assembly column, the order CPL and
the CPL audit. Checked: PROTOTYPE-LOT.md, owner-items/order/ORDER-PACKAGE.md (its current block only, the quoted lines before
the history) and CPL-PREVIEW-CHECKLIST.md.
"""
import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path


def check(root):
    err = []
    note = (root / "fab/FAB-NOTE.md").read_text()
    stage = re.search(r"Board: native-21 stage (\d+)[a-z]?, the board of record", note).group(1)
    board = re.search(r"Board: native-21 stage.*?`([0-9a-f]{64})`", note, re.S).group(1)
    remark = re.search(r"\*\*Order remarks\*\*[^\"]*\"([^\"]+)\"", note).group(1)
    zsha = hashlib.sha256((root / "fab/native-21-gerbers.zip").read_bytes()).hexdigest()
    if zsha not in note:
        err.append("FAB-NOTE.md does not carry the zip's SHA-256")
    bom = list(csv.DictReader(open(root / "fab/bom-jlcpcb.csv")))
    cpl = sum(1 for _ in csv.DictReader(open(root / "fab/cpl-jlcpcb-order.csv")))
    jlc = [r for r in bom if r["Assembly"].startswith("JLC")]
    basic = sum("Basic" in r["Assembly"] for r in jlc)
    ext = sum("Extended" in r["Assembly"] for r in jlc)
    dnp = {d for r in bom if r["Assembly"].startswith("DNP") for d in r["Designator"].split(",")}
    aud = json.loads((root / "cpl-rotation-audit/audit.json").read_text())
    n = {c: sum(r["class"] == c for r in csv.DictReader(open(root / "cpl-rotation-audit/audit.csv")))
         for c in ("OK", "CORRECTED", "NEEDS-PREVIEW")}
    exc = len(aud["excluded"])

    lot = (root / "PROTOTYPE-LOT.md").read_text()
    order = (root / "owner-items/order/ORDER-PACKAGE.md").read_text()
    cur = "\n".join(l for l in order.split("\n") if l.startswith(">"))
    flat = re.sub(r"\s+", " ", cur.replace("\n>", " "))
    chk = (root / "owner-items/order/CPL-PREVIEW-CHECKLIST.md").read_text()
    for name, t in (("PROTOTYPE-LOT.md", re.sub(r"\s+", " ", lot)), ("ORDER-PACKAGE.md", flat)):
        for what, want in (("stage", f"stage {stage}"), ("board SHA", board[:12]), ("zip SHA", zsha[:8]),
                           ("order remark", re.sub(r"\s+", " ", remark))):
            if want not in t:
                err.append(f"{name}: {what} '{want[:60]}' missing")
        for sha in set(re.findall(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])", t)) - {board, zsha}:
            err.append(f"{name}: names another file or board, {sha[:12]}")
        for ref in sorted(dnp):
            if re.search(rf"consigned[^.;]*\b{ref}\b", t, re.I) and not re.search(rf"not consigned[^.;]*\b{ref}\b|\b{ref}\b[^.;]*not consigned", t, re.I):
                err.append(f"{name}: {ref} is DNP in the BOM but described as consigned")
    if f"JLC assembles {len(jlc)} of the {len(bom)} BOM lines" not in flat:
        err.append(f"ORDER-PACKAGE.md: 'JLC assembles {len(jlc)} of the {len(bom)} BOM lines' missing")
    for want in (f"{len(bom)} BOM lines, {cpl} CPL rows", f"**{len(jlc)} lines are assembled by JLC**", f"({basic} Basic, {ext} Extended)",
                 f"OK {n['OK']} / CORRECTED {n['CORRECTED']} / NEEDS-PREVIEW **{n['NEEDS-PREVIEW']}** / excluded {exc}"):
        if want not in lot:
            err.append(f"PROTOTYPE-LOT.md: '{want}' missing")
    for want in (f"the {cpl} CPL rows", f"OK {n['OK']}, CORRECTED {n['CORRECTED']}", f"NEEDS-PREVIEW {n['NEEDS-PREVIEW']}, excluded {exc}"):
        if want not in chk:
            err.append(f"CPL-PREVIEW-CHECKLIST.md: '{want}' missing")
    return err


NEED = ["fab/FAB-NOTE.md", "fab/native-21-gerbers.zip", "fab/bom-jlcpcb.csv", "fab/cpl-jlcpcb-order.csv", "cpl-rotation-audit/audit.json",
        "cpl-rotation-audit/audit.csv", "PROTOTYPE-LOT.md", "owner-items/order/ORDER-PACKAGE.md", "owner-items/order/CPL-PREVIEW-CHECKLIST.md"]


def selftest(root):
    """Each mutation must be caught."""
    P, O = "PROTOTYPE-LOT.md", "owner-items/order/ORDER-PACKAGE.md"
    board = re.search(r"`([0-9a-f]{64})`", (root / "fab/FAB-NOTE.md").read_text()).group(1)
    muts = [("lot: old board", P, board[:12], "82af7bd93e62"), ("lot: old remark", P, "Do Not Place: leave their holes open", "seat the package"),
            ("package: old board", O, board, "82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27"),
            ("lot: FETs consigned", P, "## Parts to buy", "- Consigned: Q2 / Q3 from the lot.\n\n## Parts to buy"),
            ("package: FETs consigned", O, "> - **order remarks", "> - consigned: Q5 / Q6;\n> - **order remarks"),
            ("bom: FETs back at JLC", "fab/bom-jlcpcb.csv", '"DNP at JLC: the owner hand-solders Q2', '"JLC (Extended): Q2'),
            ("zip changed", "fab/native-21-gerbers.zip", None, None)]
    bad = 0
    for name, f, o, n in muts:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for x in NEED:
                (d / x).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(root / x, d / x)
            if o is None:
                (d / f).write_bytes((d / f).read_bytes() + b"\0")
            else:
                t = (d / f).read_text()
                assert o in t, (name, "mutation did not apply")
                (d / f).write_text(t.replace(o, n))
            ok = bool(check(d))
            bad += not ok
            print("caught" if ok else "MISSED", name)
    return bad


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    e = check(a.root)
    for x in e:
        print("FAIL:", x)
    if not e:
        print("PASS: the order documents match the board of record")
    sys.exit(1 if e or (a.selftest and selftest(a.root)) else 0)
