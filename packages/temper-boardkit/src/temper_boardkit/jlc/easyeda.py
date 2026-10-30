"""EasyEDA / LCSC part records and pad-number rotation fits (pure; Python 3.9+).

Records: <cache>/<LCSC>-product.json, the EasyEDA product API answer for the exact LCSC part.  When absent
they are fetched from the lceda.cn mirror: easyeda.com/api/products answers 403 to scripted and browser
requests since 2026-10-21, and the mirror's PAD records for C2684450 and C44853692 were identical to the
easyeda.com ones fetched the day before.  Commit the cached records: the fit is then reproducible offline.

PAD shape records: 'PAD~shape~x~y~w~h~layer~net~number~holeR~points~rotation~...', 10 mil units, canvas y down.

Two fits, both by pad number, both over quarter turns, least RMS of the pad centres after removing the
common translation:
  fit_cpl_offset(native, vendor)   JLC CPL rotation offset: native KiCad pads (footprint frame, y down) turned
                                   by R(-offset); CPL angle = (board angle + offset) % 360
  fit_rigid(native, vendor)        the 2D motion carrying vendor pads (y up) onto native pads (y up): turn
                                   and translation, for placing the vendor's 3D model
A part whose vendor pad numbers mean other pins than the KiCad footprint's needs a renumbering first
(renumber(); e.g. LCSC C2286 LED: EasyEDA 1 = anode, KiCad LED_0603 1 = cathode).
"""
from __future__ import annotations

import hashlib
import json
import math
import urllib.request
from pathlib import Path

UNIT = 0.254            # mm per EasyEDA canvas unit (10 mil)


def source_url(lcsc):
    return f'https://lceda.cn/api/products/{lcsc}/components?version=6.4.19.5'


def record(lcsc, cache_dir, fetch=True):
    """-> (result, sha256 of the cached file, file name).  Fetches into cache_dir when absent and fetch."""
    path = Path(cache_dir) / f'{lcsc}-product.json'
    if not path.exists():
        if not fetch:
            raise FileNotFoundError(path)
        req = urllib.request.Request(source_url(lcsc), headers={'User-Agent': 'Mozilla/5.0'})
        path.write_bytes(urllib.request.urlopen(req, timeout=30).read())
    raw = path.read_bytes()
    return json.loads(raw)['result'], hashlib.sha256(raw).hexdigest(), path.name


def shapes(result):
    return [item.split('~') for item in result['packageDetail']['dataStr']['shape']]


def easyeda_pads(result, y_up=False):
    """{number: (x, y)} pad centres in mm, canvas origin (y down; y_up flips y).  First record per number."""
    pads = {}
    for f in shapes(result):
        if f[0] == 'PAD' and f[8]:
            pads.setdefault(f[8], (float(f[2]) * UNIT, (-1 if y_up else 1) * float(f[3]) * UNIT))
    return pads


def pads_about_head(result):
    """{number: ((u, v), polygon or None)} in mm about the footprint's head origin, y up: the frame JLC
    places a part in from its CPL Mid X / Mid Y and Rotation.  Later records of a number win."""
    ds = result['packageDetail']['dataStr']
    hx, hy = float(ds['head']['x']), float(ds['head']['y'])
    out = {}
    for p in shapes(result):
        if p[0] == 'PAD' and p[8]:
            pts = [float(v) for v in p[10].split()] if p[10].strip() else []
            poly = ([((pts[i] - hx) * UNIT, -(pts[i + 1] - hy) * UNIT) for i in range(0, len(pts), 2)]
                    if pts else None)
            out[p[8]] = (((float(p[2]) - hx) * UNIT, -(float(p[3]) - hy) * UNIT), poly)
    return out


def model_3d(result):
    """The outline3D SVGNODE attributes (uuid, c_origin, c_rotation, z, title) or None."""
    for f in shapes(result):
        if f[0] == 'SVGNODE':
            attrs = json.loads(f[1])['attrs']
            if attrs.get('c_etype') == 'outline3D':
                return attrs
    return None


def renumber(vendor, vendor_to_kicad):
    """Vendor pad numbers -> KiCad pad numbers ({'1': '2', '2': '1'} swaps a two-pad part)."""
    return {vendor_to_kicad.get(n, n): xy for n, xy in vendor.items()}


def fit_cpl_offset(native, vendor):
    """-> (sorted [(rms, max, offset)], common pad numbers).  native: KiCad pad centres at angle 0 (footprint
    frame, y down); vendor: easyeda_pads(result) (y down).  ranked[0][2] is the CPL rotation offset."""
    common = sorted(set(native) & set(vendor))
    out = []
    for offset in (0, 90, 180, 270):
        a = math.radians(-offset)
        # native pads turned by R(-offset), KiCad y-down
        rot = {n: (x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a))
               for n, (x, y) in native.items() if n in common}
        cx = sum(p[0] for p in rot.values()) / len(rot) - sum(vendor[n][0] for n in common) / len(common)
        cy = sum(p[1] for p in rot.values()) / len(rot) - sum(vendor[n][1] for n in common) / len(common)
        err = [math.hypot(rot[n][0] - cx - vendor[n][0], rot[n][1] - cy - vendor[n][1]) for n in common]
        out.append((math.sqrt(sum(e * e for e in err) / len(err)), max(err), offset))
    return sorted(out), common


def fit_rigid(native, vendor):
    """-> (sorted [(rms, turn, tx, ty)], common).  Both y up; vendor turned by +turn then moved by (tx, ty)
    lands on native."""
    common = sorted(set(native) & set(vendor))
    best = []
    for turn in (0, 90, 180, 270):
        c, s = math.cos(math.radians(turn)), math.sin(math.radians(turn))
        rv = {n: (c * vendor[n][0] - s * vendor[n][1], s * vendor[n][0] + c * vendor[n][1]) for n in common}
        tx = sum(native[n][0] - rv[n][0] for n in common) / len(common)
        ty = sum(native[n][1] - rv[n][1] for n in common) / len(common)
        err = [math.hypot(rv[n][0] + tx - native[n][0], rv[n][1] + ty - native[n][1]) for n in common]
        best.append((math.sqrt(sum(e * e for e in err) / len(err)), turn, tx, ty))
    return sorted(best), common
