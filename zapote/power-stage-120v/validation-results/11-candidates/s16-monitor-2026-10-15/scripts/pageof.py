#!/usr/bin/env python3
"""Print the PDF page (1-based, from pdftotext form feeds) of each line matching a regex.
usage: python3 -I scripts/pageof.py dl/txt/<file>.txt '<regex>' [max]"""
import re, sys
t = open(sys.argv[1], encoding="utf-8", errors="replace").read()
n = int(sys.argv[3]) if len(sys.argv) > 3 else 5
for m in list(re.finditer(sys.argv[2], t))[:n]:
    page = t.count("\f", 0, m.start()) + 1
    line = t[t.rfind("\n", 0, m.start()) + 1: t.find("\n", m.end())].strip()
    print(f"p.{page}: {line[:150]}")
