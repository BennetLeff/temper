"""Shared inputs for the native-22 shrink floorplan and its B3 thermal gate.

Read-only on the repo. Inputs:
  RUN/section.kicad_pcb   the s53 board of record (SHA-256 checked); courtyards and poses
  GEOM                    the s53 B3 copper export (tracked; board_sha256 checked): pads with nets, vias, tracks, zones
  the shrink study's KiCad reader (output/temper-board-shrink-r1/scripts/power_board_area.py): footprint parsing, blocks
  the unit's net -> isolation domain map (native-21/layout/domains.py)

Frames: KiCad board frame, x right, y down, mm, origin at the board's top-left corner (s53 and native-22 share it: the
power core keeps its s53 coordinates). Rasters are cell-centred on a pitch grid whose origin is (0, 0).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
WT = HERE.parents[2]
UNIT = WT / "zapote/power-stage-120v"
RUN = WT.parent / "runs-native21/s53/c53int"                 # outside git, as the shrink study (r1) used it
S53_SHA = "82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27"
GEOM = UNIT / "native-21/verification/native21s53-all-copper.json.gz"
B3 = UNIT / "validation-results/04-board-current-thermal/round5-native21"
WORK = OUT / "work"                                             # regenerable, gitignored
RESULTS = OUT / "results"
RENDERS = OUT / "renders"

sys.path.insert(0, str(WT / "output/temper-board-shrink-r1/scripts"))
import power_board_area as pba  # noqa: E402

sys.path.insert(0, str(UNIT / "native-21/layout"))
import domains  # noqa: E402

PITCH = 0.25          # floorplan / territory raster [mm]
BARRIER_MM = 8.0      # HOT <-> SELV/PE copper (D5-BASIS, provisional, owner-approved floor)
S53_OUTLINE = [(290.0, 140.0), (91.0, 140.0), (91.0, 190.0), (0.0, 190.0), (0.0, 0.0), (290.0, 0.0)]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def side_of(net: str | None) -> str | None:
    """HOT side (HOT, MAINS, SW_A, SW_B) or LOW side (SELV, PE), as power_board_area.py's moat split."""
    if not net:
        return None
    d = domains.domain(net)
    return "LOW" if d in ("SELV", "PE") else "HOT"


def load_geom() -> dict:
    d = json.loads(gzip.open(GEOM, "rt").read())
    if d["board_sha256"] != S53_SHA:
        raise SystemExit(f"{GEOM} is board {d['board_sha256'][:12]}, not s53 {S53_SHA[:12]}")
    return d


def load_parts(geom: dict | None = None) -> dict:
    """ref -> part record from the s53 board of record (courtyards, pose, block) and the B3 export (pads, nets)."""
    pcb = RUN / "section.kicad_pcb"
    if sha256(pcb) != S53_SHA:
        raise SystemExit(f"{pcb} is not the s53 board of record")
    geom = geom or load_geom()
    pads = {}
    for it in geom["primitives"]:
        if it["kind"] == "pad":
            pads.setdefault(it["ref"].partition(".")[0], []).append(it)
    parts = {}
    for fp in pba.split_footprints(pcb.read_text()):
        f = pba.parse_fp(fp)
        ref = f["ref"]
        ps = pads.get(ref, [])
        sides = {side_of(p.get("net")) for p in ps} - {None}
        polys = [(ly, [tuple(map(float, q)) for q in pts]) for ly, pts in f["polys"]]
        parts[ref] = {
            "ref": ref, "source": f["source"], "block": pba.block_of(ref, f["source"]), "side": f["side"],
            "tht": "through_hole" in f["attr"], "mech": "board_only" in f["attr"], "at": list(f["at"]),
            "polys": polys, "pads": ps, "domain": "X" if sides == {"HOT", "LOW"} else (sides.pop() if sides else None),
        }
    return parts


# ---------------------------------------------------------------------------------------------- rigid transforms
def rot_xy(x, y, rot):
    """Rotate about the origin by rot (0/90/180/270 deg) in the y-down board frame, KiCad sense (CCW on screen)."""
    r = int(rot) % 360
    if r == 0:
        return x, y
    if r == 90:
        return y, -x
    if r == 180:
        return -x, -y
    if r == 270:
        return -y, x
    raise ValueError(rot)


def xf(pt, t):
    """Apply transform t = (rot, tx, ty): p' = R p + (tx, ty)."""
    x, y = rot_xy(pt[0], pt[1], t[0])
    return (x + t[1], y + t[2])


def xf_inv_arrays(xs, ys, t):
    """Inverse of xf on arrays: p = R^-1 (p' - t)."""
    return rot_xy(xs - t[1], ys - t[2], (360 - int(t[0])) % 360)


def xf_arrays(xs, ys, t):
    x, y = rot_xy(xs, ys, t[0])
    return x + t[1], y + t[2]


IDENT = (0, 0.0, 0.0)


# ---------------------------------------------------------------------------------------------- rasters
class Frame:
    def __init__(self, w, h, pitch=PITCH):
        self.w, self.h, self.p = w, h, pitch
        self.nx, self.ny = int(round(w / pitch)), int(round(h / pitch))
        self.x = (np.arange(self.nx) + 0.5) * pitch
        self.y = (np.arange(self.ny) + 0.5) * pitch

    def mask(self, shape, out=None):
        out = np.zeros((self.nx, self.ny), bool) if out is None else out
        if shape.is_empty:
            return out
        x0, y0, x1, y1 = shape.bounds
        ix = np.flatnonzero((self.x >= x0) & (self.x <= x1))
        iy = np.flatnonzero((self.y >= y0) & (self.y <= y1))
        if ix.size and iy.size:
            xx, yy = np.meshgrid(self.x[ix], self.y[iy], indexing="ij")
            out[np.ix_(ix, iy)] |= shapely.contains_xy(shape, xx, yy)
        return out


def prim_shape(it):
    k = it["kind"]
    if k in ("zone", "pad"):
        return Polygon(it["shell"], it["holes"])
    if k == "track":
        return LineString((it["start"], it["end"])).buffer(it["width_mm"] / 2, 8)
    if k == "via":
        return Point(it["centre"]).buffer(it["diameter_mm"] / 2, 16)
    return None


def courtyard_shape(polys, t=IDENT):
    sh = [Polygon([xf(p, t) for p in pts]).buffer(0) for _, pts in polys if len(pts) >= 3]
    return shapely.unary_union(sh) if sh else Polygon()


def owner_map(frame: Frame, board: np.ndarray, parts: dict, poses: dict):
    """Territory owner per cell: the part whose courtyard is nearest (Euclidean, cell centres), as the shrink study's
    territory but on the Euclidean metric. Mechanical footprints (holes, fiducials, test pads) own nothing.
    poses: ref -> transform for every part that exists on this board. Returns (owner index array (-1 off board), refs)."""
    from scipy.ndimage import distance_transform_edt
    refs = [r for r in poses if not parts[r]["mech"]]
    lab = np.full((frame.nx, frame.ny), -1, np.int32)
    order = sorted(range(len(refs)), key=lambda i: -courtyard_shape(parts[refs[i]]["polys"]).area)
    for i in order:                                    # larger first; smaller parts overwrite where courtyards overlap
        m = frame.mask(courtyard_shape(parts[refs[i]]["polys"], poses[refs[i]]))
        lab[m] = i
    if (lab < 0).all():
        raise ValueError("no courtyards")
    _, (ii, jj) = distance_transform_edt(lab < 0, return_indices=True)
    own = lab[ii, jj]
    own[~board] = -1
    return own, refs


def domain_copper(frame: Frame, geom: dict):
    """(hot, low) any-layer copper masks of the s53 export on `frame`."""
    hot = np.zeros((frame.nx, frame.ny), bool)
    low = np.zeros_like(hot)
    for it in geom["primitives"]:
        s = side_of(it.get("net"))
        if s is None:
            continue
        sh = prim_shape(it)
        if sh is None:
            continue
        frame.mask(sh, hot if s == "HOT" else low)
    return hot, low


def bbox(polys, t=IDENT):
    pts = [xf(p, t) for _, ps in polys for p in ps]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def dump(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, default=float) + "\n")
