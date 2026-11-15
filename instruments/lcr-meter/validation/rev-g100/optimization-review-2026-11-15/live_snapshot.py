"""Signed-out JLC library snapshot for every code in bom-complete.csv -> live-snapshot.json (same schema as boardkit jlc.parts)."""
import csv, json, subprocess, sys, datetime, time
W = sys.argv[1]
URL = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
parts = {}
for row in csv.DictReader(open(W + "/manufacturing/bom-complete.csv")):
    code = row["LCSC"]
    for attempt in range(3):
        out = subprocess.run(["curl", "-s", "-m", "30", "-X", "POST", "-H", "Content-Type: application/json", "-A", "Mozilla/5.0",
                              "-d", json.dumps({"keyword": code, "currentPage": 1, "pageSize": 25}), URL], capture_output=True).stdout
        try:
            hits = [c for c in json.loads(out)["data"]["componentPageInfo"]["list"] if c["componentCode"] == code]
            assert len(hits) == 1
            break
        except Exception as e:
            hits = None; time.sleep(2)
    if not hits: print("FAIL", code); continue
    c = hits[0]
    parts[code] = {"model": c["componentModelEn"], "library": c["componentLibraryType"], "preferred": bool(c["preferredComponentFlag"]),
                   "stock": c["stockCount"], "least": c["leastPatchNumber"], "loss": c["lossNumber"],
                   "tiers": [[p["startNumber"], p["productPrice"]] for p in c["componentPrices"]]}
json.dump({"fetched": datetime.datetime.now().isoformat(timespec="minutes"), "parts": parts}, open("live-snapshot.json", "w"), indent=1)
print(len(parts), "parts")
