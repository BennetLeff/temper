#!/usr/bin/env python3
"""JLC/EasyEDA pad centres for LCSC codes from the EasyEDA Pro API (easyeda.com's /api/products route 403s since
2026-10-21). POST https://pro.easyeda.com/api/v2/devices/searchByCodes -> footprint uuid; GET
https://pro.easyeda.com/api/components/<uuid> -> Pro text, PAD x/y in mil with y UP. Converted to the record format of
evidence/c51/jlc_pads.json: mm, y DOWN (y negated), which check_land_patterns.py centres before fitting.
usage: python3 -I fetch_pro_pads.py C123 [C456 ...]   (merges into jlc_pads.json here; raw replies in raw/)
       python3 -I fetch_pro_pads.py --control C7666    (compare with the committed easyeda_pads.json record)"""
import json, math, pathlib, subprocess, sys, time

HERE = pathlib.Path(__file__).resolve().parent
RAW = HERE / "raw"
OUT = HERE / "jlc_pads.json"
MIL = 0.0254
UA = "temper-parts-check"


def curl(args):
    return subprocess.run(["curl", "-s", "-m", "40", "-A", UA] + args, check=True, capture_output=True).stdout


def record(code):
    RAW.mkdir(exist_ok=True)
    s = json.loads(curl(["-X", "POST", "https://pro.easyeda.com/api/v2/devices/searchByCodes",
                         "--data-urlencode", f"codes[]={code}"]))
    (RAW / f"{code}-device.json").write_text(json.dumps(s, indent=1, ensure_ascii=False) + "\n")
    if not s.get("result"):
        return {"error": "no EasyEDA device record for this code", "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    dev = s["result"][0]
    fp = dev["footprint"]["uuid"]
    c = json.loads(curl([f"https://pro.easyeda.com/api/components/{fp}"]))
    (RAW / f"{code}-footprint.json").write_text(json.dumps(c, indent=1, ensure_ascii=False) + "\n")
    pads = []
    for line in c["result"]["dataStr"].splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if isinstance(r, list) and r and r[0] == "PAD":
            pads.append({"layer": str(r[4]), "n": str(r[5]), "x": round(r[6] * MIL, 4), "y": round(-r[7] * MIL, 4)})
    return {"package": dev["footprint"].get("display_title"), "pads": pads,
            "title": dev["attributes"].get("Manufacturer Part"), "source": "pro.easyeda.com",
            "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def centred(pads):
    cx = sum(p["x"] for p in pads) / len(pads); cy = sum(p["y"] for p in pads) / len(pads)
    return {p["n"]: (round(p["x"] - cx, 3), round(p["y"] - cy, 3)) for p in pads}


if __name__ == "__main__":
    if sys.argv[1] == "--control":
        code = sys.argv[2]
        ref = json.loads((HERE.parent / "fab-loose-ends/cpl-rotation/easyeda_pads.json").read_text())[code]
        new = record(code)
        a, b = centred(ref["pads"]), centred(new["pads"])
        err = max(math.dist(a[n], b[n]) for n in a)
        print(code, "committed", a, "\n pro", b, "\n max centre difference mm", round(err, 4))
        sys.exit(0 if set(a) == set(b) and err < 0.01 else 1)
    out = json.loads(OUT.read_text()) if OUT.exists() else {}
    miss_path = HERE / "missing.json"            # codes with no record stay out of jlc_pads.json (the land gate reads it)
    missing = json.loads(miss_path.read_text()) if miss_path.exists() else {}
    for code in sys.argv[1:]:
        rec = record(code)
        if "error" in rec:
            missing[code] = rec; out.pop(code, None)
        else:
            out[code] = rec; missing.pop(code, None)
        print(code, rec.get("error") or f'{rec["package"]} {len(rec["pads"])} pads')
        time.sleep(0.5)
    OUT.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    miss_path.write_text(json.dumps(missing, indent=1, sort_keys=True) + "\n")
