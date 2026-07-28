# Provenance: commit=UNKNOWN dirty=UNKNOWN -- backfilled prior to the provenance gate's introduction (2026-07-26); no self-declared commit exists in this file's own content and none was fabricated. See .evidence-provenance-allowlist.

"""Loop 1: does a valid board outline change the router's completion rate?

Hypothesis: the router's 3.45% completion / 326 unconnected is caused by 113 of
149 footprints sitting outside the 100x150mm placeholder Edge.Cuts outline, not
by a router defect.

Method: route the board twice -- once as-committed, once with an outline that
actually encloses the existing placement. Nothing in the repo is modified; the
variant board is written to scratchpad.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path("/Users/bennet/Desktop/temper")
SCRATCH = Path(
    "/private/tmp/claude-501/-Users-bennet-Desktop-temper/"
    "b3b19a7e-c3ff-4eab-814f-dd42fe2bd889/scratchpad"
)
PCB = REPO / "pcb" / "temper.kicad_pcb"
RULES = REPO / "packages" / "temper-placer" / "configs" / "netclass_rules.yaml"

MARGIN = 15.0  # mm of routing room around the placement bbox


def footprint_origins(src: str) -> list[tuple[str, float, float]]:
    rows = []
    for chunk in src.split("(footprint ")[1:]:
        at = re.search(r"\n\s*\(at ([\d.-]+) ([\d.-]+)", chunk)
        ref = re.search(r'\(property "Reference" "([^"]+)"', chunk)
        if at:
            rows.append(
                (ref.group(1) if ref else "?", float(at.group(1)), float(at.group(2)))
            )
    return rows


def assert_all_inside(src: str, poly: tuple[float, float, float, float]) -> None:
    """The precondition check that was missing for a month."""
    x0, y0, x1, y1 = poly
    bad = [r for r in footprint_origins(src) if not (x0 <= r[1] <= x1 and y0 <= r[2] <= y1)]
    if bad:
        raise AssertionError(
            f"{len(bad)} footprints outside outline "
            f"({x0},{y0})-({x1},{y1}): {[b[0] for b in bad[:6]]}"
        )


def rewrite_outline(src: str, x0: float, y0: float, x1: float, y1: float) -> str:
    new = (
        "  (gr_poly\n    (pts\n"
        f"      (xy {x0} {y0})\n      (xy {x1} {y0})\n"
        f"      (xy {x1} {y1})\n      (xy {x0} {y1})\n"
        '    ) (layer "Edge.Cuts") (width 0.1))'
    )
    out, n = re.subn(
        r"  \(gr_poly\s*\(pts(?:\s*\(xy [\d.-]+ [\d.-]+\))+\s*\)\s*"
        r'\(layer "Edge\.Cuts"\) \(width [\d.]+\)\)',
        new,
        src,
    )
    assert n == 1, f"expected exactly 1 Edge.Cuts gr_poly, replaced {n}"
    return out


def drc(path: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["kicad-cli", "pcb", "drc", "--format", "json", "-o", "/dev/null", str(path)],
        capture_output=True,
        text=True,
    ).stdout
    v = re.search(r"Found (\d+) violations", out)
    u = re.search(r"Found (\d+) unconnected", out)
    return (int(v.group(1)) if v else -1, int(u.group(1)) if u else -1)


def route(pcb_path: Path, label: str) -> None:
    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.io.netclass_loader import load_netclass_rules
    from temper_placer.router_v6.adapter import route_pcb

    sys.path.insert(0, str(REPO / "packages" / "temper-placer"))
    from tests.conftest import make_parsed_pcb_stub

    rules = load_netclass_rules(RULES)
    netlist = parse_kicad_pcb(pcb_path).netlist
    stub = make_parsed_pcb_stub(pcb_path, netlist)

    print(f"\n=== {label} ===")
    print(f"  components: {len(netlist.components)}")
    t0 = time.monotonic()
    res = route_pcb(stub, {}, design_rules=rules.design_rules, enable_zone_pours=True)
    print(f"  wall: {time.monotonic() - t0:.1f}s")
    print(f"  completion_rate: {res.completion_rate:.4f}")

    tmp = Path(tempfile.mkstemp(suffix=".kicad_pcb")[1])
    tmp.write_text(res.routed_pcb_content or "")
    viol, unconn = drc(tmp)
    print(f"  DRC violations: {viol}   unconnected: {unconn}")
    print(f"  segments emitted: {(res.routed_pcb_content or '').count('(segment')}")


def main() -> None:
    src = PCB.read_text()
    rows = footprint_origins(src)
    xs = [r[1] for r in rows]
    ys = [r[2] for r in rows]
    print(f"placement bbox: x {min(xs):.1f}..{max(xs):.1f}  y {min(ys):.1f}..{max(ys):.1f}")

    # Baseline: as committed.
    try:
        assert_all_inside(src, (0, 0, 100, 150))
        print("baseline precondition: PASS")
    except AssertionError as e:
        print(f"baseline precondition: FAIL -- {e}")

    # Variant: outline that actually encloses the placement.
    x0, y0 = min(xs) - MARGIN, min(ys) - MARGIN
    x1, y1 = max(xs) + MARGIN, max(ys) + MARGIN
    variant = rewrite_outline(src, round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1))
    assert_all_inside(variant, (x0, y0, x1, y1))
    print(f"variant outline: ({x0:.1f},{y0:.1f})-({x1:.1f},{y1:.1f})  precondition: PASS")

    vpath = SCRATCH / "temper_valid_outline.kicad_pcb"
    vpath.write_text(variant)

    route(PCB, "BASELINE (100x150 placeholder outline)")
    route(vpath, "VARIANT (outline encloses placement)")


if __name__ == "__main__":
    main()
