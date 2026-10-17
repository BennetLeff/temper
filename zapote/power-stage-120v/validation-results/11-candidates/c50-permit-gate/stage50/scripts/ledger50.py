#!/usr/bin/env python3
"""Stage 50 datasheet-ledger edit (c50-permit-gate: U46.A gated by PERMIT through R135 100 k).

    python3 -I validation-results/11-candidates/c50-permit-gate/stage50/scripts/ledger50.py
        -> native-21/verification/datasheet-ledger/ledger.json (in place)

* R135 (hb.rgate) leaves 0603WAF1002T5E (10 k) for 0603WAF1003T5E (100 k), the existing line (same UniRoyal 0603 sheet,
  same ratings). Its stress is 3.47 V over 100 k = 0.12 mW (PERMIT high, U46.A input current ~0): the line's derating row
  is set by R128 (3.94 mW), so R135 adds nothing to it. R135's local temperature (temp-ratings 2026-10-15, s48 board, the
  SELV pocket) is 65.1 / 60.0 / 61.4 C at c17.5 / c22 / c28, below the line's worst ref R128 (98.5 / 98.2 / 107.9 C); the
  line's worst-of-N stress rows stand as they are and the R135 values are noted.
* SN74LVC1G132DBVR function text: U46 was "gated by HS-B's ISO7710F verdict" (stage 30 text, stale since stage 40). It is
  the SELV heartbeat NAND, input A (hsb_good, U46.1) driven from PERMIT through R135 100 k, input B the CA-IS3720 heartbeat.
Re-running it on the edited ledger gives the same file.
"""
import sys as _s; _s.dont_write_bytecode = True
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = HERE.parents[4]
LEDGER = PS / "native-21/verification/datasheet-ledger/ledger.json"
NOTE = ("S50 (2026-10-16, 11-candidates/c50-permit-gate): R135 (hb.rgate) joins from 0603WAF1002T5E as U46.A's 100 k "
        "series resistor from PERMIT; 3.47 V / 100 k = 0.12 mW, temp-ratings R135 pad 65.1 / 60.0 / 61.4 C "
        "(c17.5 / c22 / c28, s48 board), inside this line's R128 rows.")
U46_OLD = "U46: SELV Schmitt NAND, heartbeat gated by HS-B's ISO7710F verdict, driving the pump"
U46_NEW = ("U46: SELV Schmitt NAND, heartbeat (B, U46.2) gated by PERMIT through R135 100 k (A, U46.1 on hsb_good; stage 50, "
           "c50-permit-gate), driving the pump")
F100_OLD = "100 k 0603 pull; stage 48: R136 / R138 / R140 / R142 are the LDO EN divider tops (IN to EN)"
F100_NEW = F100_OLD + "; stage 50: R135 is U46.A's series resistor from PERMIT"


def main():
    led = json.loads(LEDGER.read_text())
    E = led["entries"]
    ten, hund, g132 = E["0603WAF1002T5E"], E["0603WAF1003T5E"], E["SN74LVC1G132DBVR"]
    if "R135" in ten["designators"]:
        ten["designators"].remove("R135")
    if "R135" not in hund["designators"]:
        hund["designators"].append("R135")
    if hund["function"] == F100_OLD:
        hund["function"] = F100_NEW
    assert hund["function"] == F100_NEW, hund["function"]
    if NOTE not in (hund.get("notes") or ""):
        hund["notes"] = ((hund.get("notes") or "") + " " + NOTE).strip()
    if U46_OLD in g132["function"]:
        g132["function"] = g132["function"].replace(U46_OLD, U46_NEW)
    assert U46_NEW in g132["function"] and "ISO7710F" not in g132["function"], g132["function"]
    LEDGER.write_text(json.dumps(led, indent=1) + "\n")
    print("ledger50: R135 -> 0603WAF1003T5E (", len(hund["designators"]), "refs ); 0603WAF1002T5E", len(ten["designators"]),
          "refs; U46 function text updated")


if __name__ == "__main__":
    main()
