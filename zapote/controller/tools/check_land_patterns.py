#!/usr/bin/env python3
"""Compare each part's KiCad footprint pads with JLC's own footprint for the same LCSC code (netlist level).

Pads are matched by number; the JLC set is centred and rotated in 90 degree steps, and the RMS distance between
matching pad centres must be <= LIMIT_MM. A part with no JLC record, or different pad numbers, is a failure unless it
is named in EXCEPTIONS with a basis; an exception that no longer matches a fitted part is also a failure.
It compares pad centres only: land sizes, courtyard and 3-D are not checked.
usage: python3 tools/check_land_patterns.py        (writes evidence/land-patterns.json)
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

UNIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(UNIT / "evidence/fab-loose-ends/cpl-rotation"))
import kicad_pads as kp  # noqa: E402
from netlist import attach_resolved, read_netlist  # noqa: E402

LIMIT_MM = 0.30
PADS = [UNIT / "evidence/fab-loose-ends/cpl-rotation/easyeda_pads.json", UNIT / "evidence/c51/jlc_pads.json",
        UNIT / "evidence/c52/jlc_pads.json"]
STOCK = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
LIBS = [UNIT / "pcb/libs", UNIT / "layout/footprints", UNIT.parent / "rtd/unit/candidate/candidate-libs", STOCK]
EXCEPTIONS: dict[str, str] = {
    "AF0603FR-0734K8L": "EasyEDA Pro has no device record for C2098331 (evidence/c52/jlc_pads.json, 2026-11-26); 0603 chip "
                        "on the stock R_0603 land, the land the RC0603FR part it replaces passed on",
    "SWPA6045S100MT": "inner pad edges agree (KiCad 1.40 mm, JLC 1.37 mm from centre); JLC's land only reaches further "
                      "outside the 6.0 mm body (3.84 against 3.10 mm)",
    "TC2050-IDC-NL-LAND": "flush probe land, no part is placed",
}


def jlc_pads() -> dict:
    out = {}
    for p in PADS:
        out.update(json.loads(p.read_text()))
    return out


def kicad_pads(footprint: str) -> list[dict]:
    lib, name = footprint.split(":", 1)
    for base in LIBS:
        f = base / f"{lib}.pretty" / f"{name}.kicad_mod"
        if f.exists():
            pads = []
            for c in kp.parse(f.read_text(encoding="utf-8")):
                if isinstance(c, list) and c and c[0] == "pad" and c[1]:
                    at = next(q for q in c if isinstance(q, list) and q[0] == "at")
                    pads.append({"n": c[1], "x": float(at[1]), "y": float(at[2])})
            return pads
    raise FileNotFoundError(footprint)


def _centres(pads) -> dict[str, tuple[float, float]]:
    g: dict[str, list] = {}
    for p in pads:
        if p["n"]:
            g.setdefault(str(p["n"]), []).append((p["x"], p["y"]))
    return {n: (sum(x for x, _ in v) / len(v), sum(y for _, y in v) / len(v)) for n, v in g.items()}


def fit(kpads, jpads) -> float:
    """RMS pad-centre distance at the best 90 degree rotation; inf when the pad numbers differ."""
    k, j = _centres(kpads), _centres(jpads)
    if set(k) != set(j) or len(k) < 2:
        return float("inf")
    n = len(k)
    kc = [sum(v[i] for v in k.values()) / n for i in (0, 1)]
    jc = [sum(v[i] for v in j.values()) / n for i in (0, 1)]
    best = float("inf")
    for c in (0, 90, 180, 270):
        a = math.radians(c)
        s = 0.0
        for m in k:
            x, y = j[m][0] - jc[0], j[m][1] - jc[1]
            s += (x * math.cos(a) + y * math.sin(a) - k[m][0] + kc[0]) ** 2 \
                + (-x * math.sin(a) + y * math.cos(a) - k[m][1] + kc[1]) ** 2
        best = min(best, math.sqrt(s / n))
    return best


def run(drop: set[str] = frozenset(), exceptions: dict[str, str] | None = None) -> dict:
    exc = EXCEPTIONS if exceptions is None else exceptions
    nl = attach_resolved(read_netlist(UNIT / "frozen/default.net"), UNIT / "frozen/resolved-components.json")
    table = json.loads((UNIT / "bom/controller-parts.json").read_text())["parts"]
    jlc = {c: v for c, v in jlc_pads().items() if c not in drop}
    pairs: dict[tuple[str, str], list[str]] = {}
    for ref, mpn in nl.mpn.items():
        pairs.setdefault((mpn, nl.footprint[ref]), []).append(ref)
    rows, failed, used = [], [], set()
    for (mpn, fp), refs in sorted(pairs.items()):
        code = table.get(mpn, {}).get("lcsc")
        rec = jlc.get(code)
        r = fit(kicad_pads(fp), rec["pads"]) if rec else None
        why = "no JLC footprint record" if rec is None else \
            "pad numbers differ" if r == float("inf") else f"misfit {r:.2f} mm" if r > LIMIT_MM else None
        if why and mpn in exc:
            used.add(mpn)
        elif why:
            failed.append(f"{mpn} {fp} {sorted(refs)[:4]}: {why}")
        rows.append({"mpn": mpn, "lcsc": code, "footprint": fp, "jlc_package": rec and rec.get("package"),
                     "refs": sorted(refs), "rms_mm": None if r in (None, float("inf")) else round(r, 3),
                     "exception": exc.get(mpn) if why else None})
    failed += [f"stale exception {m}" for m in exc if m not in used]
    return {"limit_mm": LIMIT_MM, "checked": sum(x["rms_mm"] is not None for x in rows), "rows": rows, "failed": failed}


def main() -> int:
    rep = run()
    (UNIT / "evidence/land-patterns.json").write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n")
    print(f"land patterns: {rep['checked']} of {len(rep['rows'])} parts compared")
    for f in rep["failed"]:
        print("FAIL", f)
    print("LAND PATTERNS:", "FAIL" if rep["failed"] else "PASS")
    return 1 if rep["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
