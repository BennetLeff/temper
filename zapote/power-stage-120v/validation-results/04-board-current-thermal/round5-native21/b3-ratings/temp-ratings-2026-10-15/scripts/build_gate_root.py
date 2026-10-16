#!/usr/bin/env python3
"""Build a scratch unit root for the ledger gate: every file the ledger's evidence cites, extracted read-only from PS
HEAD with `git archive` (no worktree writes), plus the temp-ratings results at their proposed home.

    python3 -I scripts/build_gate_root.py LEDGER_JSON [LEDGER_JSON ...]
-> ../gate-root/zapote/power-stage-120v/...
"""
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate")
UNIT = "zapote/power-stage-120v"
OUT = ROOT / "gate-root"
PATH_RE = re.compile(r"(?<![\w/.\-])([A-Za-z0-9_./+\-]+\.(?:md|py|json|ato|csv|txt|pdf|yaml|sh|rs))"
                     r"(?::(\d+)(?:[\-–](\d+))?)?")          # gate.py PATH_RE
HOME = "validation-results/04-board-current-thermal/round5-native21/b3-ratings/temp-ratings-2026-10-15"


def walk(o, acc):
    if isinstance(o, dict):
        if isinstance(o.get("file"), str):
            acc.add(o["file"])
        for v in o.values():
            walk(v, acc)
    elif isinstance(o, list):
        for v in o:
            walk(v, acc)
    elif isinstance(o, str):
        acc.update(m.group(1) for m in PATH_RE.finditer(o))


def main():
    paths = {"native-21/frozen/default.csv"}
    for f in sys.argv[1:]:
        walk(json.loads(Path(f).read_text()), paths)
    tracked = set(subprocess.run(["git", "-C", str(REPO), "ls-tree", "-r", "--name-only", "HEAD", "--", UNIT],
                                 capture_output=True, text=True, check=True).stdout.split())
    want = sorted(p for p in paths if f"{UNIT}/{p}" in tracked)
    absent = sorted(p for p in paths if f"{UNIT}/{p}" not in tracked and not p.startswith(HOME))
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    blob = subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", "HEAD", "--"] + [f"{UNIT}/{p}" for p in want],
                          capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(blob)) as t:
        t.extractall(OUT, filter="data")
    home = OUT / UNIT / HOME
    home.mkdir(parents=True, exist_ok=True)
    for f in ("results.json", "results.md"):
        shutil.copy(ROOT / f, home / f)
    (home / "scripts").mkdir(exist_ok=True)
    for f in ("temp_ratings.py", "ratings_table.py", "power_table.py", "ledger_temps.py"):
        if (HERE / f).exists():
            shutil.copy(HERE / f, home / "scripts" / f)
    print(f"gate root: {len(want)} files from HEAD, {len(absent)} cited paths not tracked at HEAD: {absent[:20]}")


if __name__ == "__main__":
    main()
