#!/usr/bin/env python3
"""Compare two runs of the native-21 chain artefacts for the stage-33 layer-stack refactor (REFACTOR-PROOF.md).

    python3 refactor_compare.py A B [A2 B2 ...]          pairs of files (or two directories: every common file)
    python3 refactor_compare.py --pcb A.kicad_pcb B.kicad_pcb

Exit 1 on any difference. Normalisation (and nothing else):
  * JSON (.json / .json.gz): keys in PROVENANCE are dropped at any depth: hashes of the scripts / inputs that the
    refactor itself edits or that carry the board's random UUIDs, git revision / dirty flags, absolute run paths.
    Every number is compared exactly (no tolerance).
  * .kicad_pcb: (uuid ...) / (tstamp ...) lines removed and the top-level items sorted (KiCad orders footprints by
    their random UUIDs, which every build draws afresh). "nofill" also drops (filled_polygon ...) blocks: KiCad's
    refill is not bit-reproducible from identical inputs (stage 22, regate.sh), so a fresh build is compared on its
    inputs (footprints, tracks, vias, zone outlines and rules) and the fill on the same-input re-evaluation.
    return_path19's "track" ints (CPython id() of a track object) are dropped too.
  * Gerber ZIP: per member, the %TF.CreationDate / drill-file date lines removed.
  * input paths under the worktrees: reduced to their file name.
  * anything else: bytes, date lines ("Created on ...", Gerber / drill creation dates) removed.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path

PROVENANCE = {
    "board_sha256", "computed_on_board", "reused_for_boards",       # random footprint UUIDs per build
    "script_sha256", "kit_sha256", "extractor_sha256", "stackup_sha256",   # the refactored scripts / stackup file
    "geometry_sha256", "input_sha256", "case_json_sha256", "heat_npz_sha256", "output_sha256",  # files that embed the above
    "source_revision", "source_dirty", "commit", "dirty",           # git state at run time
    "key",                                                          # chain cache keys (hash of the scripts)
}


def norm(o):
    if isinstance(o, dict):
        # return_path19 tags rows with "track": id(track), a CPython memory address (differs run to run)
        return {k: norm(v) for k, v in o.items() if k not in PROVENANCE and not (k == "track" and isinstance(v, int))}
    if isinstance(o, list):
        return [norm(v) for v in o]
    if isinstance(o, str) and o.startswith("/Users/bennet/Desktop/temper/worktrees/"):
        # an input path: only its file name is content (the run directory differs by construction)
        base = o.rstrip("/").rsplit("/", 1)[-1]
        return "<RUN>/" + base if "." in base else "<RUN>"
    return o


def first_diffs(a, b, path="", out=None, limit=8):
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if type(a) is not type(b):
        out.append(f"{path}: type {type(a).__name__} != {type(b).__name__}")
    elif isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{path}/{k}: only in {'B' if k not in a else 'A'}")
            else:
                first_diffs(a[k], b[k], f"{path}/{k}", out, limit)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} != {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            first_diffs(x, y, f"{path}[{i}]", out, limit)
    elif a != b:
        out.append(f"{path}: {str(a)[:80]} != {str(b)[:80]}")
    return out


def load_json(p: Path):
    raw = gzip.open(p, "rt").read() if p.suffix == ".gz" else p.read_text()
    return json.loads(raw)


def pcb_items(p: Path, nofill=False):
    text = p.read_text()
    if nofill:
        text = re.sub(r"\n\t\t\(filled_polygon\n.*?\n\t\t\)(?=\n)", "", text, flags=re.S)
    lines = [ln for ln in text.split("\n") if not re.match(r'^\s*\((uuid|tstamp) "[^"]*"\)\s*$', ln)]
    items, cur = [], []
    for ln in lines[1:]:
        if ln.startswith("\t(") and cur:
            items.append("\n".join(cur))
            cur = []
        cur.append(ln)
    if cur:
        items.append("\n".join(cur))
    return sorted(items)


def pcb_hash(p: Path, nofill=False) -> str:
    return hashlib.sha256("\n".join(pcb_items(p, nofill)).encode()).hexdigest()


DATE = re.compile(rb"^(%TF\.CreationDate.*|Created on .*|; #@! TF\.CreationDate.*|G04 Created by KiCad.*date.*|;DRILL file .* date .*"
                  rb"|; DRILL file .* date .*|.*\"CreationDate\".*)$", re.M)


def zip_members(p: Path) -> dict:
    with zipfile.ZipFile(p) as z:
        return {n: hashlib.sha256(DATE.sub(b"", z.read(n))).hexdigest() for n in sorted(z.namelist())}


def compare(a: Path, b: Path):
    """Return (equal, description)."""
    name = a.name
    if name.endswith(".kicad_pcb"):
        full = pcb_hash(a) == pcb_hash(b)
        nofill = pcb_hash(a, True) == pcb_hash(b, True)
        return full or nofill, (f"pcb uuid-normalised {'EQUAL' if full else 'differs'}; without zone fills "
                                f"{'EQUAL' if nofill else 'DIFFERS'} ({pcb_hash(a, True)[:12]} / {pcb_hash(b, True)[:12]})")
    if name.endswith(".zip"):
        ma, mb = zip_members(a), zip_members(b)
        bad = sorted(k for k in set(ma) | set(mb) if ma.get(k) != mb.get(k))
        return not bad, f"{len(ma)} members, date-normalised: " + ("EQUAL" if not bad else f"differ {bad[:6]}")
    if name.endswith(".json") or name.endswith(".json.gz"):
        ja, jb = norm(load_json(a)), norm(load_json(b))
        if ja == jb:
            return True, "json (provenance-normalised) EQUAL"
        return False, "json differs: " + "; ".join(first_diffs(ja, jb))
    eq = DATE.sub(b"", a.read_bytes()) == DATE.sub(b"", b.read_bytes())
    return eq, "bytes (date lines removed) " + ("EQUAL" if eq else "differ")


def main(argv):
    if argv and argv[0] == "--pcb":
        a, b = map(Path, argv[1:3])
        print(pcb_hash(a), pcb_hash(a, True), a)
        print(pcb_hash(b), pcb_hash(b, True), b)
        return 0
    pairs = []
    args = [Path(x) for x in argv]
    if len(args) == 2 and args[0].is_dir():
        common = sorted({p.name for p in args[0].iterdir() if p.is_file()} & {p.name for p in args[1].iterdir() if p.is_file()})
        pairs = [(args[0] / n, args[1] / n) for n in common]
    else:
        pairs = list(zip(args[::2], args[1::2]))
    bad = 0
    for a, b in pairs:
        ok, why = compare(a, b)
        bad += not ok
        print(f"{'EQUAL' if ok else 'DIFF '}  {a.name:45s} {why}")
    print("ALL EQUAL" if not bad else f"{bad} DIFFERENT")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
