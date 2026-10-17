#!/usr/bin/env python3
"""Read-only fetch of the public EasyEDA/LCSC footprint + symbol pin data for every LCSC number in
fab/bom-jlcpcb.csv, distilled to pad geometry in sources/easyeda-footprints.json.

    python3 -I fetch_easyeda.py [--offline] [raw-cache-dir]

Source: JLCEDA/EasyEDA Official Library (https://lceda.cn/, https://easyeda.com), public component
API, GET only. The endpoint rate-limits (HTTP 403) after ~50 requests; the script backs off and
retries, and reuses raw JSON already present in the cache dir. Not needed for a normal audit.py
rerun (sources/ is committed)."""
import csv, json, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOM = HERE.parent / "fab" / "bom-jlcpcb.csv"
OUT = HERE / "sources" / "easyeda-footprints.json"
HOST = "lceda.cn"      # same JLCEDA official library; easyeda.com answers 403 after ~50 requests
UNIT = 0.254  # EasyEDA canvas unit = 10 mil


def get(lcsc, cache, offline=False):
    f = cache / f"{lcsc}.json"
    for attempt in range(1 if offline else 5):
        if f.exists() and f.read_bytes()[:1] == b"{":
            return json.loads(f.read_text())
        if offline:
            return None
        time.sleep(20 * (attempt + 1))
        subprocess.run(["curl", "-sL", "-m", "40", "-H", "User-Agent: curl/8.4.0", "--compressed",
                        f"https://{HOST}/api/products/{lcsc}/components?version=6.4.19.5",
                        "-o", str(f)], check=False)
    return None


def distill(d):
    r = d["result"]
    pk = r["packageDetail"]["dataStr"]
    pads = []
    for s in pk["shape"]:
        if s.startswith("PAD~"):
            f = s.split("~")
            pads.append({"shape": f[1], "x": float(f[2]) * UNIT, "y": float(f[3]) * UNIT,
                         "w": float(f[4]) * UNIT, "h": float(f[5]) * UNIT, "layer": f[6],
                         "num": f[8], "hole_r": float(f[9] or 0) * UNIT,
                         "rot": float(f[11] or 0) if len(f) > 11 else 0.0})
    pins = []
    for s in r["dataStr"]["shape"]:
        if s.startswith("P~"):
            segs = s.split("^^")
            h = segs[0].split("~")
            nm = segs[3].split("~")[4] if len(segs) > 3 else ""
            pins.append({"num": h[3], "name": nm})
    return {"title": r.get("title"), "package": pk["head"]["c_para"].get("package"),
            "model3d": pk["head"]["c_para"].get("3DModel"), "pads": pads, "pins": pins}


def main():
    offline = "--offline" in sys.argv          # distill only what is already in the cache dir
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cache = Path(args[0]) if args else Path("ee-raw")
    cache.mkdir(parents=True, exist_ok=True)
    ids = sorted({r["LCSC Part #"] for r in csv.DictReader(BOM.open()) if r["LCSC Part #"]})
    out = {}
    for i in ids:
        d = get(i, cache, offline)
        if d is None or not d.get("success", True) or "result" not in d:
            out[i] = {"error": "not available from the EasyEDA component API"}
            print(i, "unavailable")
            continue
        out[i] = distill(d)
    OUT.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(len(out), "LCSC parts ->", OUT)


if __name__ == "__main__":
    main()
