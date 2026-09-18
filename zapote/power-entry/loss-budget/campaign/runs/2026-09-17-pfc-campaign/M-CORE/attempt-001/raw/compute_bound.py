#!/usr/bin/env python3
"""M-CORE attempt-001 -- core + AC-winding loss bound arithmetic.

Source-only task.  This script performs NO model invocation and fits nothing.
It encodes only numbers that are (a) supplied by the dispatch/prior tasks, and
(b) published by a manufacturer source captured in raw/.  Where an input is
unpublished it stays None and is reported as such.

Run:
    python3 raw/compute_bound.py            # prints JSON to stdout
    python3 raw/compute_bound.py --out raw/computed_bound.json
"""

import argparse
import json
import math

MU0 = 4.0e-7 * math.pi

# --- Operating envelope (dispatch / F-AXIS report) ---------------------------
ENVELOPE = {
    "i_rms_a": 15.0,
    "i_peak_a": 23.2719,
    "ripple_pp_a": 4.2043,
    "f_hz": {"M065": 65000.0, "M090": 90000.0},
    "source": "F-AXIS/attempt-001/raw/report.json via M065/M090 dispatch",
}

# --- Switching saving vs. retained 760800301 (maintained model, prior tasks) --
SWITCHING_SAVING_W = {"M065": 19.3765, "M090": 11.8202}

# --- Choke data: DC terms from prior sourcing tasks (M065, M090) --------------
# L_at_bias is the *typical* digitized datasheet curve; DCR is datasheet max @20C.
CHOKES = {
    "760800301": {  # retained baseline, T75
        "size_type": "T75",
        "L_nom_uH": 180.0,
        "L_at_bias_uH": 159.8,
        "dcr_max_mohm": 20.0,
        "isat_typ_a": 43.0,
    },
    "760801202": {  # M065 candidate, T50
        "size_type": "T50",
        "L_nom_uH": 389.0,
        "L_at_bias_uH": 350.1,
        "dcr_max_mohm": 50.0,
        "isat_typ_a": 37.0,
    },
    "760801403": {  # M090 candidate, T37
        "size_type": "T37",
        "L_nom_uH": 355.0,
        "L_at_bias_uH": 242.7,
        "dcr_max_mohm": 35.0,
        "isat_typ_a": 23.0,
    },
}

# Part envelope (datasheet page-1 drawing, external dimensions).
ENVELOPE_DIMS_MM = {"T37": (53.0, 50.0), "T50": (72.0, 45.0), "T75": (99.0, 62.0)}

# --- Material data (manufacturer-published) ----------------------------------
# Wurth family statement: WE-TORPFC uses High Flux (Ni-Fe) and Sendust (Al-Si-Fe)
# cores.  No per-part material mapping is published.
# Magnetics (core manufacturer) High Flux: Bsat 15,000 gauss = 1.5 T, Ni-Fe.
BSAT_CEILING_T = 1.5  # max over the family's candidate materials (High Flux)
# Magnetics High Flux permeability grades available (mu).  Used only to bracket
# the energy-density argument, NOT as this part's permeability.
MU_GRADES = (14.0, 160.0)


def dc_copper_w(dcr_mohm, i_rms):
    return i_rms * i_rms * dcr_mohm * 1e-3


def flux_swing_upper_bound_t(i_peak, ripple_pp, bsat_ceiling):
    """Geometry-free upper bound on the peak-to-peak flux swing.

    For any magnetic core, B <= Bsat.  With B(I) = mu0*mu_r(H)*H and
    L(I)*I = N*Ae*B(I)  (exact for a uniform-B toroid), we get
        N*Ae = L(I)*I / B(I)  >= L(I_pk)*I_pk / Bsat
    so the swing dB = L(I_pk)*dI/(N*Ae) <= dI*Bsat/I_pk.
    L cancels; this holds for any inductance.  It is a *loose* ceiling: the
    peak of the datasheet L(I) curve is well below Bsat for 760801202.
    """
    return ripple_pp * bsat_ceiling / i_peak


def energy_j(L_uH, i_peak):
    return 0.5 * L_uH * 1e-6 * i_peak * i_peak


def ve_min_m3(energy_j, bsat_ceiling_t, mu_grade):
    """Lower bound on core volume from the magnetic-energy density ceiling.

    W = Ve * u, u = B^2/(2*mu0*mu_r) <= Bsat^2/(2*mu0*mu_min)
    => Ve >= W * 2*mu0*mu_min / Bsat^2.
    Uses the smallest permeability grade -> the smallest (most conservative)
    lower bound, so the resulting Ve range is never understated.
    """
    return energy_j * 2.0 * MU0 * mu_grade / (bsat_ceiling_t ** 2)


def ve_envelope_upper_m3(size_type, dims_mm):
    od, h = dims_mm[size_type]
    return (math.pi / 4.0) * (od * 1e-3) ** 2 * (h * 1e-3)  # bounding cylinder


def main():
    out = {
        "schema": "pfc-campaign-core-ac-bound/v1",
        "task_id": "M-CORE",
        "attempt_id": "attempt-001",
        "model_invocations": 0,
        "envelope": ENVELOPE,
        "material_ceiling": {
            "Bsat_ceiling_T": BSAT_CEILING_T,
            "basis": "Magnetics High Flux (Ni-Fe) published saturation flux density "
                     "15,000 gauss = 1.5 T; highest of the family's candidate "
                     "materials (High Flux Ni-Fe / Sendust Al-Si-Fe).",
            "used_for": "upper bound on flux swing only; not a per-part material claim.",
        },
        "flux_swing": {},
        "core_loss": {},
        "ac_winding_loss": {},
        "verdict_inputs": {},
    }

    i_pk = ENVELOPE["i_peak_a"]
    d_ipp = ENVELOPE["ripple_pp_a"]
    bsat = BSAT_CEILING_T

    db_ub = flux_swing_upper_bound_t(i_pk, d_ipp, bsat)
    out["flux_swing"]["upper_bound_T"] = db_ub
    out["flux_swing"]["derivation"] = (
        "dB <= dI * Bsat_ceiling / I_pk  =  %.4f * %.1f / %.4f = %.5f T  "
        "(geometry- and L-independent)" % (d_ipp, bsat, i_pk, db_ub)
    )
    out["flux_swing"]["lower_bound_T"] = None
    out["flux_swing"]["lower_bound_reason"] = (
        "No published N*Ae upper bound exists, so the flux swing cannot be "
        "bounded from below; a watts-level core-loss bound needs both."
    )

    # Per-candidate DC terms, headroom, energy and Ve bracket.
    for mpn, c in CHOKES.items():
        dc = dc_copper_w(c["dcr_max_mohm"], ENVELOPE["i_rms_a"])
        W = energy_j(c["L_at_bias_uH"], i_pk)
        vmin = min(ve_min_m3(W, bsat, mu) for mu in MU_GRADES)
        vmax = ve_envelope_upper_m3(c["size_type"], ENVELOPE_DIMS_MM)
        out["core_loss"][mpn] = {
            "L_at_bias_uH": c["L_at_bias_uH"],
            "magnetic_energy_J": W,
            "core_volume_lower_bound_m3": vmin,
            "core_volume_envelope_upper_bound_m3": vmax,
            "core_volume_range_ratio": vmax / vmin,
            "core_loss_W": None,
            "core_loss_reason": (
                "Core volume is unestablished over a %.0fx range (energy floor vs "
                "dimensional envelope) and the per-part core material is unpublished, "
                "so a published loss-density curve cannot be converted to watts."
                % (vmax / vmin)
            ),
        }
        out["ac_winding_loss"][mpn] = {
            "Rac_over_Rdc": None,
            "reason": "No AC-resistance / skin-proximity data at 65-90 kHz is "
                      "published for any WE-TORPFC part; wire thickness and turns "
                      "are not published, so Rac/Rdc cannot be bounded.",
        }
        out["verdict_inputs"][mpn] = {
            "dc_copper_w_at_20C": dc,
            "switching_saving_w": (
                SWITCHING_SAVING_W["M065"] if mpn == "760801202"
                else SWITCHING_SAVING_W["M090"]
            ),
            "headroom_for_core_plus_ac_w": None,
        }

    # Headroom (candidate delta vs baseline DC).
    base_dc = dc_copper_w(CHOKES["760800301"]["dcr_max_mohm"], 15.0)
    for mpn, case in (("760801202", "M065"), ("760801403", "M090")):
        dc = dc_copper_w(CHOKES[mpn]["dcr_max_mohm"], 15.0)
        delta = dc - base_dc
        out["verdict_inputs"][mpn]["dc_delta_vs_baseline_w"] = delta
        out["verdict_inputs"][mpn]["headroom_for_core_plus_ac_w"] = (
            SWITCHING_SAVING_W[case] - delta
        )

    out["bound"] = {
        "core_plus_ac_upper_bound_W": None,
        "reason": (
            "Not constructible from primary sources. The flux swing is bounded above "
            "only, and the core volume needed to convert published loss density to "
            "watts is unestablished; the per-part core material is unpublished. "
            "A lower bound (>= DC copper only) does not exceed the headroom either."
        ),
    }
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    result = main()
    text = json.dumps(result, indent=2)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(text + "\n")
        print("wrote", args.out)
    else:
        print(text)
