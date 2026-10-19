#!/usr/bin/env python3
"""M11 heatsink-stack build: can each stack part reach its installed position along a straight path?

    $CAD/bin/python check_stack_build.py [--r43 DIR] [--explore] [--controls] [--out result.json]

Needs build123d 0.11.1 (a scratch venv: `uv venv -p 3.12 cadenv && VIRTUAL_ENV=cadenv uv pip install build123d==0.11.1`).
Reads the R43 STEP parts and `catalog.json` read-only (R43 is a frozen revision: nothing is written there) and writes `result.json` here.

The existing R43 checker (`src/check_assembly_sequence.py`) moves the whole stack up 120 mm as ONE rigid bench subassembly. This
checks the stack's own build, on the bench, before that: the native-21 board with its FETs is fixed on a fixture and each stack
part is swept in along a stated direction against everything installed before it. Same screen as the R43 checker: 5 mm steps far out, 1 mm
within 20 mm of the seat, then 0.5 mm; a per-solid bounding-box prune, then an exact intersection volume above 0.01 mm3. A pair that R43's
metadata or COMPLIANT below accepts as overlapping AT THE SEAT (a proxy envelope against a part, a compressing pad) is allowed to overlap by
no more than its seated volume (+0.5 mm3) anywhere on the path; R43's own checker skips those pairs outright, which makes every sweep against them blind.

Direction names say where the part arrives FROM: `+Z` means it starts above its seat and moves down.

Not modelled: the comb spring's deflection, adhesive or paste, the tools, and tolerance stack-up. The FETs are the R43 components
ENVELOPE proxy (not the real TO-247 outline), so a clear sweep is necessary evidence, not proof.
"""
import argparse
import hashlib
import json
from pathlib import Path

import build123d as bd

HERE = Path(__file__).resolve().parent
DEFAULT_R43 = Path.home() / "Desktop/temper/output/temper-manufacturing-r43"      # the R43 folder is not in git; pass --r43 elsewhere

BOARD = ["electronics_native21_board", "electronics_native21_components_ENVELOPE"]       # on the fixture: installed first
SINK = "electronics_native21_sink_ENVELOPE"
BAR = "electronics_sink_spreader_bar"
TILES = ["electronics_sink_AlN_tile_A", "electronics_sink_AlN_tile_B"]
STRIP = "electronics_sink_FR4_pressure_strip"
COMB = "electronics_sink_clamp_comb"
GAP = "electronics_sink_BR1_gap_pad"
SCREWS = "electronics_sink_bar_bond_screws_M4"
DIRS = {"+X": (1, 0, 0), "-X": (-1, 0, 0), "+Y": (0, 1, 0), "-Y": (0, -1, 0), "+Z": (0, 0, 1), "-Z": (0, 0, -1)}
# the stack axis in the R43 pose is +Y (board edge at Y 236; strip behind the FET bodies, tiles on the tabs, then bar and sink)
COMPLIANT = {frozenset((COMB, STRIP)), frozenset((GAP, BAR)), frozenset((GAP, SINK)), frozenset((GAP, TILES[1])),
             frozenset((SCREWS, BAR)), frozenset((SCREWS, SINK))}

# (title, parts, direction name, travel mm). The proposed bench order; edit after the build is decided.
SEQUENCE = [
    ("Tiles A and B lowered onto the FET / BR1 tab faces (held by hand or tape)", TILES, "+Z", 60),
    ("BR1 gap pad lowered", [GAP], "+Z", 40),
    ("FR-4 pressure strip lowered behind the FET bodies", [STRIP], "+Z", 60),
    ("Spreader bar with the sink envelope (one PE metal subassembly), brought up to the tiles from the sink side", [BAR, SINK], "+Y", 80),
    ("Clamp comb lowered over the strip and the bar", [COMB], "+Z", 60),
    ("Bar bond screws M4 driven along +Y from the board side, above the comb (they lie along Y; from above they hit the sink)", [SCREWS], "-Y", 60),
]


def poses(travel):
    steps = sorted({*range(int(travel), 20, -5), *range(20, 0, -1), 0.5, 0.0}, reverse=True)
    return steps


def vol(s):
    return 0.0 if s is None else (sum(i.volume for i in s) if isinstance(s, bd.ShapeList) else s.volume)


class Stack:
    def __init__(self, r43):
        self.r43 = Path(r43)
        cat = {p["name"]: p for p in json.loads((self.r43 / "catalog.json").read_text())}
        meta = json.loads((self.r43 / "evidence/subsystem-metadata.json").read_text())
        sup = json.loads((self.r43 / "evidence/harness/supplemental-proxy-dispositions.json").read_text())
        self.skip = {frozenset(r["pair"]) for sec in meta.values() for r in sec.get("expected_interferences", [])}
        self.skip |= {frozenset(r["pair"]) for r in sup["expected_interferences"]} | COMPLIANT
        self.shape, self.box = {}, {}
        for n in BOARD + TILES + [SINK, BAR, STRIP, COMB, GAP, SCREWS]:
            f = self.r43 / cat[n]["file"]
            assert hashlib.sha256(f.read_bytes()).hexdigest() == cat[n]["sha256"], n
            self.shape[n] = bd.import_step(f)
            self.box[n] = self.shape[n].bounding_box()
        self.solids = {n: [(x, x.bounding_box()) for x in self.shape[n].solids()] for n in self.shape}
        self._seat = {}

    def overlap(self, moved_solids, other):
        """Total intersection volume of the moved part's solids with `other`'s solids (per-solid bbox prune)."""
        total = 0.0
        for ms, ma in moved_solids:
            for os_, ob in self.solids[other]:
                if any(getattr(ma.max, ax) <= getattr(ob.min, ax) + 1e-6 or getattr(ob.max, ax) <= getattr(ma.min, ax) + 1e-6 for ax in "XYZ"):
                    continue
                total += vol(ms.intersect(os_))
        return total

    def seat_overlap(self, name, other):
        key = (name, other)
        if key not in self._seat:
            self._seat[key] = self.overlap(self.solids[name], other)
        return self._seat[key]

    def sweep(self, name, direction, travel, installed):
        """Return (farthest-out collision offset in mm or None if clear to the seat, worst hit) for a part arriving from `direction`."""
        d = DIRS[direction]
        hits = []
        for t in poses(travel):
            moved = [(bd.Pos(*(c * t for c in d)) * x) for x, _ in self.solids[name]]
            moved = [(m, m.bounding_box()) for m in moved]
            for other in installed:
                accepted = frozenset((name, other)) in self.skip
                allowed = (self.seat_overlap(name, other) + 0.5) if accepted else 0.01
                v = self.overlap(moved, other)
                if v > allowed:
                    hits.append({"offset_mm": t, "installed": other, "volume_mm3": round(v, 3), "allowed_mm3": round(allowed, 3)})
        if not hits:
            return None, None
        first = max(h["offset_mm"] for h in hits)
        worst = max(hits, key=lambda h: h["volume_mm3"])
        return first, worst


def run_sequence(s):
    installed, report = list(BOARD), []
    for title, parts, direction, travel in SEQUENCE:
        blocked = []
        for p in parts:
            others = installed + [q for q in parts if q != p and parts.index(q) < parts.index(p)]
            first, worst = s.sweep(p, direction, travel, others)
            if first is not None:
                blocked.append({"part": p, "collides_from_mm": first, "worst": worst})
        installed += parts
        report.append({"title": title, "parts": parts, "direction": direction, "travel_mm": travel, "blocked": blocked})
        print(("BLOCKED " if blocked else "clear   ") + title, flush=True)
        for b in blocked:
            print("    ", b["part"], "collides from", b["collides_from_mm"], "mm out with", b["worst"]["installed"], "(%s mm3)" % b["worst"]["volume_mm3"])
    return report


def explore(s):
    """For each stack part, with the board and every OTHER stack part already installed except those that come after it in the
    proposed order, which directions are clear to the seat? (Order-free view: installed = board only, then = the proposed predecessors.)"""
    out = {}
    done = list(BOARD)
    for title, parts, _, _ in SEQUENCE:
        for p in parts:
            row = {}
            for dn in DIRS:
                first, worst = s.sweep(p, dn, 80, done)
                row[dn] = "clear" if first is None else "blocked from %.1f mm by %s" % (first, worst["installed"])
            out[p] = {"installed_before": [x for x in done], "directions": row}
        done += parts
    return out


def controls(s):
    """Known-bad sweeps that MUST be blocked, and one that must be clear:
    - tile A arriving from the board side (-Y) runs through the FET bodies;
    - the FR-4 strip arriving from the tile side (+Y) runs through the FET bodies;
    - tile A arriving from above (+Z) with only the board installed is the intended path, so it must be clear."""
    c1, _ = s.sweep(TILES[0], "-Y", 40, BOARD)
    c2, _ = s.sweep(STRIP, "+Y", 40, BOARD)
    c3, _ = s.sweep(TILES[0], "+Z", 60, BOARD)
    return {"tile_from_board_side_blocked": c1 is not None, "strip_from_tile_side_blocked": c2 is not None, "tile_from_above_clear": c3 is None}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--r43", default=str(DEFAULT_R43))
    ap.add_argument("--explore", action="store_true")
    ap.add_argument("--controls", action="store_true")
    ap.add_argument("--out", default=str(HERE / "result.json"))
    a = ap.parse_args()
    s = Stack(a.r43)
    res = {"r43": str(Path(a.r43).name), "sequence": run_sequence(s)}
    if a.controls:
        res["controls"] = controls(s)
        print("controls:", res["controls"])
    if a.explore:
        res["explore"] = explore(s)
    res["status"] = "CLEAR" if not any(r["blocked"] for r in res["sequence"]) else "REVIEW_REQUIRED"
    Path(a.out).write_text(json.dumps(res, indent=1) + "\n")
    print(res["status"])
