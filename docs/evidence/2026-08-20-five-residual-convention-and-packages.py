# provenance: commit=30edd0a93cd4843b16bcc361c53fb02727511231 dirty=false
# provenance: board sha256 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b
# Read-only with respect to pcb/temper.kicad_pcb: the board is parsed, never
# opened for write, and its sha256 is asserted before and after. No threshold,
# ceiling, ratchet, allowlist or oracle is read for modification or written.
"""Three independent checks that back the enumeration.

1. R(-THETA) vs R(+THETA) decided AGAIN, here, from this board's own routed
   copper: KiCad anchors a track on a pad centre, so a candidate centre that
   coincides with a same-net segment endpoint or via centre is evidence.
2. Per-isolator INTRA-PACKAGE worst HV<->SELV span under the canonical
   composition -- a rigid-body invariant, so no placement can change it.
   This is the "no placement helps" class.
3. Scope: how many pad-carrying nets the domain manifest does not classify,
   i.e. what the census cannot see.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import yaml
from kiutils.board import Board

import temper_placer.core.insulation_coordination as ic
from temper_placer.core.pad_geometry import DEFAULT_ROUNDRECT_RATIO, pad_pair_distance

BOARD = Path("pcb/temper.kicad_pcb")
EPS = 1e-6


def main() -> None:
    before = hashlib.sha256(BOARD.read_bytes()).hexdigest()
    print(f"board sha256 BEFORE: {before}")
    b = Board.from_file(str(BOARD))

    # ---------- 1. convention, from routed copper ----------
    anchors: dict[str, set[tuple[float, float]]] = {}
    for item in b.traceItems:
        net = getattr(item, "net", None)
        name = None
        if isinstance(net, int):
            name = next((n.name for n in b.nets if n.number == net), None)
        elif net is not None:
            name = getattr(net, "name", None)
        if name is None:
            continue
        s = anchors.setdefault(name, set())
        for attr in ("start", "end", "position"):
            p = getattr(item, attr, None)
            if p is not None:
                s.add((round(p.X, 4), round(p.Y, 4)))
    print(f"routed-copper anchor points on {len(anchors)} nets")

    minus_only = plus_only = both = neither = 0
    for fp in b.footprints:
        fang = float(fp.position.angle or 0.0)
        if round(fang) % 180 == 0:  # the two matrices agree at 0 and 180
            continue
        fx, fy = fp.position.X, fp.position.Y
        am, ap = math.radians(-fang), math.radians(fang)
        for pad in fp.pads:
            if pad.net is None or pad.net.name not in anchors:
                continue
            lx, ly = float(pad.position.X), float(pad.position.Y)
            cm = (round(fx + lx * math.cos(am) - ly * math.sin(am), 4),
                  round(fy + lx * math.sin(am) + ly * math.cos(am), 4))
            cp = (round(fx + lx * math.cos(ap) - ly * math.sin(ap), 4),
                  round(fy + lx * math.sin(ap) + ly * math.cos(ap), 4))
            hm, hp = cm in anchors[pad.net.name], cp in anchors[pad.net.name]
            if hm and not hp:
                minus_only += 1
            elif hp and not hm:
                plus_only += 1
            elif hm and hp:
                both += 1
            else:
                neither += 1
    print(f"  R(-theta) matched where R(+theta) did not : {minus_only}")
    print(f"  R(+theta) matched where R(-theta) did not : {plus_only}")
    print(f"  both matched: {both}   neither matched: {neither}")

    # ---------- 2. intra-package HV<->SELV spans ----------
    dm = yaml.safe_load(Path("elec/domain_manifest.yaml").read_text(encoding="utf-8"))
    hv = frozenset(dm["domains"]["HV"]["nets"])
    selv = frozenset(dm["domains"]["SELV"]["nets"])

    print("\nper-isolator INTRA-PACKAGE worst HV<->SELV span "
          "(rigid-body invariant -- no placement changes it)")
    print(f"  {'ref':6} {'footprint':44} {'pairing':18} {'fig':>6} {'worst span':>11} {'verdict':>10}")
    for fp in b.footprints:
        ref = (fp.properties or {}).get("Reference") or "?"
        fang = float(fp.position.angle or 0.0)
        am = math.radians(-fang)
        fx, fy = fp.position.X, fp.position.Y
        specs = []
        for pad in fp.pads:
            net = pad.net.name if pad.net is not None else ""
            if net not in hv and net not in selv:
                continue
            lx, ly = float(pad.position.X), float(pad.position.Y)
            rr = getattr(pad, "roundrectRatio", None)
            specs.append((
                str(pad.number), net, net in hv,
                (float(pad.size.X), float(pad.size.Y),
                 str(getattr(pad, "shape", None) or "rect"),
                 fx + lx * math.cos(am) - ly * math.sin(am),
                 fy + lx * math.sin(am) + ly * math.cos(am),
                 math.radians(float(pad.position.angle or 0.0)),
                 DEFAULT_ROUNDRECT_RATIO if rr is None else float(rr)),
            ))
        hvp = [s for s in specs if s[2]]
        sep = [s for s in specs if not s[2]]
        if not hvp or not sep:
            continue
        worst = None
        for a in hvp:
            for c in sep:
                d = pad_pair_distance(a[3], c[3])
                pr = ic.requirement_for_nets(a[1], c[1])
                short = pr.enforceable_floor_mm() - d
                if worst is None or short > worst[0]:
                    worst = (short, d, pr, a, c)
        short, d, pr, a, c = worst
        name = f"{fp.libraryNickname}:{fp.entryName}" if fp.libraryNickname else fp.entryName
        verdict = "SHORT" if short > EPS else ("clears" if pr.is_determinable() else "above floor")
        print(f"  {ref:6} {name:44} {pr.key():18} {pr.enforceable_floor_mm():6.2f} "
              f"{d:11.4f} {verdict:>12}   binding {ref}.{a[0]}<->{ref}.{c[0]} "
              f"({a[1]} <-> {c[1]}), short {short:+.4f}, determinable={pr.is_determinable()}")

    # ---------- 3. scope ----------
    nets_with_pads: dict[str, int] = {}
    for fp in b.footprints:
        for pad in fp.pads:
            if pad.net is not None and pad.net.name:
                nets_with_pads[pad.net.name] = nets_with_pads.get(pad.net.name, 0) + 1
    undeclared = {n: k for n, k in nets_with_pads.items() if n not in hv and n not in selv}
    print("\nscope of the census:")
    print(f"  pad-carrying nets on the board        : {len(nets_with_pads)}")
    print(f"  declared HV                           : {len([n for n in nets_with_pads if n in hv])}")
    print(f"  declared SELV                         : {len([n for n in nets_with_pads if n in selv])}")
    print(f"  in NEITHER domain (census cannot see) : {len(undeclared)} "
          f"nets / {sum(undeclared.values())} pads")

    after = hashlib.sha256(BOARD.read_bytes()).hexdigest()
    print(f"\nboard sha256 AFTER : {after}")
    if after != before:
        raise SystemExit("BOARD WAS MODIFIED")


if __name__ == "__main__":
    main()
