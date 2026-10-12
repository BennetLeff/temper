#!/usr/bin/env python3
"""Read-only: fetch public EasyEDA/LCSC footprint pad geometry and distil it to pad numbers + positions.

Source: https://easyeda.com/api/products/<LCSC>/components  (public, unauthenticated, rate-limited: the
server answers 403 after ~20 requests, so this backs off and resumes). Footprint data (c) JLCEDA/EasyEDA
Official Library, https://easyeda.com , https://lceda.cn .  Raw JSON stays in --raw-dir (never committed);
only the derived numbers (pad number, x, y in mm, top/through layer) go to easyeda_pads.json.
usage: easyeda_pads.py --raw-dir <fresh dir> [--fetch] [--out easyeda_pads.json]
"""
import argparse, csv, json, os, pathlib, subprocess, time

HERE = pathlib.Path(__file__).resolve().parent
BOM = HERE.parents[2] / "fab" / "bom-jlcpcb.csv"
MM = 0.254  # EasyEDA footprint unit is 10 mil


def fetch(raw, codes):
    """Fetch each missing code once; 404 'Component not found' is final, 403/other is rate limiting -> back off."""
    back = 60
    while True:
        todo = []
        for c in codes:
            p = raw / f"{c}.json"
            if p.exists() and (p.stat().st_size > 1000 or b'"code":404' in p.read_bytes()):
                continue
            todo.append(c)
        if not todo:
            return
        c = todo[0]
        p = raw / f"{c}.json"
        subprocess.run(["curl", "-sL", "-m", "40", "-o", str(p), f"https://easyeda.com/api/products/{c}/components"])
        if p.stat().st_size > 1000 or b'"code":404' in p.read_bytes():
            back = 60
            time.sleep(4)
        else:
            print("rate-limited at", c, len(todo), "left; waiting", back, "s", flush=True)
            time.sleep(back)
            back = min(back * 2, 600)


def distil(path):
    d = json.load(open(path))["result"]
    pd = d["packageDetail"]
    pads = []
    for s in pd["dataStr"]["shape"]:
        f = s.split("~")
        if f[0] == "PAD":
            pads.append({"n": f[8], "x": round(float(f[2]) * MM, 4), "y": round(float(f[3]) * MM, 4), "layer": f[6]})
    return {"title": d.get("title"), "package": pd.get("title"), "updateTime": pd.get("updateTime"),
            "url": "https://easyeda.com/api/products/%s/components" % os.path.basename(path)[:-5], "pads": pads}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", required=True)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--out", default=str(HERE / "easyeda_pads.json"))
    a = ap.parse_args()
    raw = pathlib.Path(a.raw_dir)
    raw.mkdir(parents=True, exist_ok=True)
    codes = sorted({r["LCSC Part #"] for r in csv.DictReader(open(BOM))})
    if a.fetch:
        fetch(raw, codes)
    out = {}
    for c in codes:
        p = raw / f"{c}.json"
        if p.exists() and p.stat().st_size > 1000:
            out[c] = distil(p)
    json.dump(out, open(a.out, "w"), indent=1, sort_keys=True)
    print(len(out), "of", len(codes), "footprints distilled ->", a.out)


if __name__ == "__main__":
    main()
