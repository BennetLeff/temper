# provenance: agent/hole-edge-placement-constraints, stacked on
# agent/per-pairing-placement-route @ bc3a19b06. Board sha256
# 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b,
# verified unmodified before and after every run. See
# docs/evidence/2026-08-19-hole-geometry-placement-constraints.md
"""Strip all routed copper (segments/vias/zones) from a board -> bare placement.

Uses scripts/route_board.py's OWN strip_existing_copper -- the same function
the production router calls before every route -- so a "bare" board here is
byte-for-byte the input the router actually starts from.
Read-only with respect to the source board (sha256 verified before/after).
"""
import argparse
import hashlib
import sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--board", type=Path, required=True)
ap.add_argument("--output", type=Path, required=True)
ap.add_argument("--repo", type=Path, default=Path.cwd())
args = ap.parse_args()
if args.output.resolve() == args.board.resolve():
    ap.error("--output must not be the input board")
sys.path.insert(0, str(args.repo / "scripts"))
from route_board import strip_existing_copper

src, dst = args.board, args.output
before = hashlib.sha256(src.read_bytes()).hexdigest()
text = src.read_text(encoding="utf-8")
cleaned, n = strip_existing_copper(text)
dst.write_text(cleaned, encoding="utf-8")
after = hashlib.sha256(src.read_bytes()).hexdigest()
assert before == after, "SOURCE MODIFIED"
print(f"{src.name}: sha256 {before[:16]} unchanged; stripped {n} items -> {dst}")
print(f"  segments {cleaned.count('(segment ')}  vias {cleaned.count('(via ')}  zones {cleaned.count('(zone ')}")
