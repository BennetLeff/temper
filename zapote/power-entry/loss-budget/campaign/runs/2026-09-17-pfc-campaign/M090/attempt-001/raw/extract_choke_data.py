#!/usr/bin/env python3
"""Reproducible extraction for M090 choke screen.

Renders page 2 of each retained WE-TORPFC datasheet, digitizes the published
"Typical Inductance vs. Current" curve, and computes the envelope DC loss
terms.  Core/AC loss are NOT published in these datasheets and are reported
as null (never inferred from DCR).

Run from this directory:
    python3 raw/extract_choke_data.py
Outputs: raw/extraction.json
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = Path(__file__).resolve().parent
PDFDIR = HERE

# part -> datasheet, L_nom_uH, DCR_max_mOhm@20C, IR_A(no fan), IR2_A(4m/s fan),
#         ISAT_A(typ), tol_pct, size, revision, curve calibration
# Calibration: x0_px at I=0, px per A ; y0_px at L=0, px per uH ;
#              x_span_A, y_span_uH (plot limits, used only to bound the search)
PARTS = {
    "760800301": dict(l_nom=180, dcr=20.0, ir=24.5, ir2=48.0, isat=43.0,
                      tol=20, size="T75", rev="001.001 / 2023-12-11",
                      x0=469.6, xpa=(1846 - 699) / 100.0, y0=1795.5,
                      ypu=(1531 - 473) / 200.0, xmax=120, ymax=250),
    "760801101": dict(l_nom=255, dcr=36.0, ir=11.2, ir2=21.7, isat=24.0,
                      tol=20, size="T43", rev="001.001 / 2023-12-11",
                      x0=702 - (1856 - 702) / 5.0, xpa=(1856 - 702) / 50.0,
                      y0=473 + (1357 - 473) / 200.0 * 300.0,
                      ypu=(1357 - 473) / 200.0, xmax=60, ymax=300),
    "760801403": dict(l_nom=355, dcr=35.0, ir=12.3, ir2=24.6, isat=23.0,
                      tol=20, size="T37", rev="001.001 / 2023-12-11",
                      x0=702 - (1856 - 702) / 5.0, xpa=(1856 - 702) / 50.0,
                      y0=473 + (1465 - 473) / 300.0 * 400.0,
                      ypu=(1465 - 473) / 300.0, xmax=60, ymax=400),
    "760801202": dict(l_nom=389, dcr=50.0, ir=11.5, ir2=20.0, isat=37.0,
                      tol=20, size="T50", rev="001.001 / 2023-12-11",
                      x0=699 - (1846 - 699) / 5.0, xpa=(1846 - 699) / 100.0,
                      y0=473 + (1503 - 473) / 350.0 * 450.0,
                      ypu=(1503 - 473) / 350.0, xmax=120, ymax=450),
    "760800202": dict(l_nom=389, dcr=50.0, ir=11.5, ir2=20.0, isat=19.0,
                      tol=20, size="T50", rev="001.001 / 2023-12-11",
                      x0=747 - (1846 - 747) / 4.0, xpa=(1846 - 747) / 80.0,
                      y0=473 + (1503 - 473) / 350.0 * 450.0,
                      ypu=(1503 - 473) / 350.0, xmax=100, ymax=450),
}

I_RMS = 15.0
I_PK = 23.2719
RIPPLE = 4.2043
TARGET_EFF_UH = 258.215
ALPHA_CU = 0.00393  # per K


def render(pdf: Path) -> Path:
    out = Path(tempfile.mkdtemp()) / "p2"
    subprocess.run(["pdftoppm", "-f", "2", "-l", "2", "-r", "300", "-png",
                    str(pdf), str(out)], check=True)
    return next(out.parent.glob("p2-*.png"))


def digitize(pdf: Path, c: dict):
    img = np.array(Image.open(render(pdf)).convert("L"))
    x_left = int(c["x0"]) + 8
    x_right = int(c["x0"] + c["xpa"] * c["xmax"]) - 3
    y_top = int(c["y0"] - c["ypu"] * c["ymax"]) + 5
    y_bot = int(c["y0"]) - 8
    m = np.zeros_like(img, dtype=bool)
    m[y_top:y_bot, x_left:x_right] = img[y_top:y_bot, x_left:x_right] < 80
    lab, n = ndimage.label(m, structure=np.ones((3, 3)))
    if n == 0:
        raise RuntimeError("no curve component found")
    sizes = ndimage.sum(np.ones_like(lab), lab, range(1, n + 1))
    comp = lab == (int(np.argmax(sizes)) + 1)
    def L(I):
        xpx = int(round(c["x0"] + c["xpa"] * I))
        rows = np.where(comp[:, xpx])[0]
        if len(rows) == 0:
            return None
        return round((c["y0"] - (rows.min() + rows.max()) / 2.0) / c["ypu"], 1)
    grid = [2.0, 5.0, 10.0, 15.0, 20.0, 23.2719, 25.0, 30.0]
    return {str(g): L(g) for g in grid}


def dc_loss(dcr_mohm, ir, ir2):
    r = dcr_mohm / 1000.0
    p20 = I_RMS ** 2 * r
    dt_nofan = 40.0 * (I_RMS / ir) ** 2
    dt_fan = 40.0 * (I_RMS / ir2) ** 2
    p_hot_nofan = I_RMS ** 2 * r * (1 + ALPHA_CU * dt_nofan)
    p_hot_fan = I_RMS ** 2 * r * (1 + ALPHA_CU * dt_fan)
    return dict(dcr_max_mohm=dcr_mohm, p_dc_w_20c=round(p20, 3),
                dt_nofan_k_est=round(dt_nofan, 1),
                dt_fan_k_est=round(dt_fan, 1),
                p_dc_w_hot_nofan_est=round(p_hot_nofan, 3),
                p_dc_w_hot_fan_est=round(p_hot_fan, 3))


def main():
    out = {}
    for part, c in PARTS.items():
        pdf = PDFDIR / f"{part}.pdf"
        rec = {k: c[k] for k in ("l_nom", "dcr", "ir", "ir2", "isat", "tol",
                                 "size", "rev")}
        rec["L_uH_vs_current_digitized"] = digitize(pdf, c)
        lp = rec["L_uH_vs_current_digitized"]["23.2719"]
        rec["L_uH_at_23p2719A"] = lp
        rec["pct_of_nominal_at_peak"] = (round(100.0 * lp / c["l_nom"], 1)
                                         if lp else None)
        rec["pct_vs_258p215_target"] = (round(100.0 * (lp - TARGET_EFF_UH)
                                              / TARGET_EFF_UH, 1) if lp else None)
        rec.update(dc_loss(c["dcr"], c["ir"], c["ir2"]))
        rec["ac_winding_loss_w_at_90kHz"] = None
        rec["ac_winding_loss_reason"] = (
            "not published in datasheet; no winding-AC-loss curve or "
            "Rac/Rdc(f) data provided")
        rec["core_loss_w_at_90kHz"] = None
        rec["core_loss_reason"] = (
            "not published in datasheet; no core-loss curve, no core material "
            "or Steinmetz data provided; not inferred from DCR")
        out[part] = rec
    (HERE / "extraction.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
