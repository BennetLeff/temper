#!/usr/bin/env python3
"""Gate: no two different-net pours on one layer closer than their clearance at the same priority (KiCad's fill
order would decide the contested copper; stage 17b).   python3 zone_priority_gate.py [copper.json]   (exit 1 on any)"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import patches21  # noqa: E402

zones = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else HERE.parent / "copper.json").read_text())["zones"]
pairs = patches21.contested_pairs(zones)
bad = [(zones[i]["layer"], zones[i].get("name"), zones[j].get("name"), zones[i].get("priority", 1))
       for i, j, _ in pairs if zones[i].get("priority", 1) == zones[j].get("priority", 1)]
print(json.dumps({"contested_pairs": len(pairs), "equal_priority": bad}))
sys.exit(1 if bad else 0)
