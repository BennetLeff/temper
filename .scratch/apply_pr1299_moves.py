#!/usr/bin/env python3
"""Apply PR #1299's 5 proposed component moves to a SCRATCH COPY of
pcb/temper.kicad_pcb. Never touches the tracked board file.

Moves (from PR #1299 body, docs/evidence/2026-08-17-pd3-creepage-12-
reexamination.md):
  C22  (68.490,189.100,270) -> (68.490,191.100,270)
  C1   (51.490,214.220,90)  -> (52.490,214.720,90)
  C6   (65.990,201.760,270) -> (66.990,201.510,270)
  R51  (33.230,97.290,90)   -> (34.730,97.290,90)
  U27  (34.100,47.960,90)   -> (33.100,47.960,90)
"""
import re
import sys
from pathlib import Path

SRC = Path("/home/bennet/Desktop/temper-wt-agent-routing-completeness-recon/pcb/temper.kicad_pcb")
DST = Path("/home/bennet/Desktop/temper-wt-agent-routing-completeness-recon/.scratch/temper-pr1299-moved.kicad_pcb")

MOVES = {
    "C22": ((68.490, 189.100, 270), (68.490, 191.100, 270)),
    "C1": ((51.490, 214.220, 90), (52.490, 214.720, 90)),
    "C6": ((65.990, 201.760, 270), (66.990, 201.510, 270)),
    "R51": ((33.230, 97.290, 90), (34.730, 97.290, 90)),
    "U27": ((34.100, 47.960, 90), (33.100, 47.960, 90)),
}


def fmt_at(x: float, y: float, r: float) -> str:
    def f(v: float) -> str:
        s = f"{v:.6f}".rstrip("0").rstrip(".")
        return s if s else "0"
    if r == 0:
        return f"(at {f(x)} {f(y)})"
    return f"(at {f(x)} {f(y)} {f(r)})"


def extract_top_level_blocks(content: str, keyword: str) -> list[tuple[int, int, str]]:
    """Return (start_line_idx, end_line_idx_inclusive, block_text) for every
    top-level (keyword ...) block, paren-depth tracked."""
    pattern = re.compile(r"^\s*\(" + re.escape(keyword) + r"\s")
    lines = content.split("\n")
    blocks = []
    cur: list[str] = []
    depth = 0
    in_block = False
    start = 0
    for i, line in enumerate(lines):
        if not in_block and pattern.match(line):
            in_block = True
            depth = 0
            cur = []
            start = i
        if in_block:
            cur.append(line)
            depth += line.count("(") - line.count(")")
            if depth <= 0:
                in_block = False
                blocks.append((start, i, "\n".join(cur)))
    return blocks


def main() -> int:
    content = SRC.read_text(encoding="utf-8")
    lines = content.split("\n")

    footprints = extract_top_level_blocks(content, "footprint")
    applied: dict[str, tuple] = {}

    for start, end, block in footprints:
        m = re.search(r'\(property "Reference" "([^"]+)"\)', block)
        if not m:
            continue
        ref = m.group(1)
        if ref not in MOVES:
            continue
        expected_old, new = MOVES[ref]
        # Find the (at ...) line -- the footprint's own placement, which is
        # the FIRST "(at " occurrence at 4-space indent directly inside the
        # footprint block (pads have their own nested "(at ...)" too, but
        # those are indented further and come after the footprint's own).
        block_lines = block.split("\n")
        at_line_idx = None
        for j, bl in enumerate(block_lines):
            am = re.match(r"^(\s*)\(at ([\-\d.]+) ([\-\d.]+)(?: ([\-\d.]+))?\)\s*$", bl)
            if am:
                at_line_idx = j
                indent = am.group(1)
                old_x, old_y = float(am.group(2)), float(am.group(3))
                old_r = float(am.group(4)) if am.group(4) else 0.0
                break
        if at_line_idx is None:
            print(f"WARNING: no (at ...) line found for {ref}, skipping", file=sys.stderr)
            continue
        exp_x, exp_y, exp_r = expected_old
        if abs(old_x - exp_x) > 1e-3 or abs(old_y - exp_y) > 1e-3 or abs(old_r - exp_r) % 360 > 1e-3:
            print(
                f"WARNING: {ref} current position ({old_x},{old_y},{old_r}) "
                f"!= PR #1299's expected old position {expected_old} -- "
                "board may have moved since that PR was written. Applying "
                "the DELTA from PR #1299 relative to the CURRENT position "
                "instead of the literal target, to stay correct either way.",
                file=sys.stderr,
            )
            dx = new[0] - exp_x
            dy = new[1] - exp_y
            new_x, new_y, new_r = old_x + dx, old_y + dy, new[2]
        else:
            new_x, new_y, new_r = new

        new_at_line = indent + fmt_at(new_x, new_y, new_r)
        global_line_idx = start + at_line_idx
        assert re.match(r"^\s*\(at ", lines[global_line_idx]), (
            f"line mismatch for {ref}: {lines[global_line_idx]!r}"
        )
        lines[global_line_idx] = new_at_line
        applied[ref] = (old_x, old_y, old_r, new_x, new_y, new_r)

    missing = set(MOVES) - set(applied)
    if missing:
        print(f"ERROR: refs not found/applied: {missing}", file=sys.stderr)
        return 1

    DST.write_text("\n".join(lines), encoding="utf-8")
    print(f"Applied {len(applied)} moves, wrote {DST}")
    for ref, (ox, oy, orot, nx, ny, nr) in applied.items():
        print(f"  {ref}: ({ox},{oy},{orot}) -> ({nx},{ny},{nr})")

    # sanity: source untouched
    import hashlib
    h = hashlib.sha256(SRC.read_bytes()).hexdigest()
    print(f"SRC sha256 (must be unchanged): {h}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
