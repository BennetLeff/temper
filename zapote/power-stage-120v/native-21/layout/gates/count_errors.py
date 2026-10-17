#!/usr/bin/env python3
"""Count error-severity DRC violations in a kicad-cli DRC JSON.   python3 count_errors.py drc.json"""
import json
import sys

d = json.load(open(sys.argv[1]))
print(sum(1 for v in d["violations"] if v["severity"] == "error"))
