#!/usr/bin/env python3
"""Switch cost per board (4 devices) at 20 boards (80 pcs) and 500 boards (2000 pcs) from the DigiKey list-price read
of 2026-10-27 (market/distributor-2026-10-27.csv; [VEN, 2026-10-27], list prices, not quotes; no Mouser data).
Break used = the largest DigiKey break at or below the quantity (the CSV's own columns). Stock against the 80 / 2000
pieces needed is reported as it was read.

    python3 -I c70_cost.py   -> ../results/cost.json
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import C55  # noqa: E402

PARTS = ["IPW65R018CFD7XKSA1", "IPW65R018CM8XKSA1", "IMW65R026M2HXKSA1", "C3M0025065D", "NTHL032N065M3S",
         "IHW40N65R6XKSA1", "IHW40N65R5XKSA1", "TP65H035G4WS"]
BASE = "IPW65R018CFD7XKSA1"


def main():
    rows = {r["mpn"]: r for r in csv.DictReader((C55 / "market/distributor-2026-10-27.csv").open())
            if r["distributor"] == "DigiKey"}
    out = {"source": "market/distributor-2026-10-27.csv (DigiKey list prices, read 2026-10-27 local) [VEN, 2026-10-27]",
           "parts": {}}
    b = rows[BASE]
    b20, b500 = 4 * float(b["price_at_qty_80"]), 4 * float(b["price_at_qty_2000"])
    for mpn in PARTS:
        r = rows[mpn]
        p20, p500 = 4 * float(r["price_at_qty_80"]), 4 * float(r["price_at_qty_2000"])
        out["parts"][mpn] = {"unit_80": float(r["price_at_qty_80"]), "break_80": r["break_used_80"],
                             "unit_2000": float(r["price_at_qty_2000"]), "break_2000": r["break_used_2000"],
                             "per_board_20": round(p20, 2), "per_board_500": round(p500, 2),
                             "delta_vs_cfd7_20": round(p20 - b20, 2), "delta_vs_cfd7_500": round(p500 - b500, 2),
                             "stock": r["stock"], "lead_time": r["factory_lead_time"], "lifecycle": r["lifecycle"]}
    (C55 / "results").mkdir(exist_ok=True)
    (C55 / "results/cost.json").write_text(json.dumps(out, indent=1) + "\n")
    for k, v in out["parts"].items():
        print(f"{k:22s} {v['per_board_20']:7.2f} {v['per_board_500']:7.2f} {v['delta_vs_cfd7_500']:+7.2f}  {v['stock']} / {v['lead_time']}")


if __name__ == "__main__":
    main()
