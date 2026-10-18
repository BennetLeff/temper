"""Material data for the coil-r1 model. Every value is a handbook/datasheet figure or a labelled ASSUMPTION.

Resistivities (20 C, Ohm m) - handbook values, as used in the repo's earlier studies where they overlap:
  copper (IACS) 1.724e-8, alpha 0.00393 /K
  5052-H32 4.99e-8 (35 % IACS; enclosure study 06)            1100 2.9e-8 (study 06)
  3003-H14 4.3e-8 (40 % IACS)                                 304 stainless 7.2e-7 (non-magnetic)
  430 ferritic stainless 6.0e-7                               low-carbon steel (1008-1010) 1.4e-7 - 1.7e-7
  grey cast iron 0.6e-6 - 1.1e-6 (carbon / silicon dependent; nominal 0.9e-6)
Pan permeability is the big unknown (ASSUMED): a ferromagnetic pan is nonlinear and hysteretic; at the LCR meter's
small signal it behaves like its initial/reversible permeability (order 100-300 for steels, lower for grey iron), at
full power like a secant permeability at the surface field (2-8 kA/m -> B 1.2-1.6 T -> mu 150-600). The model sweeps
mu 50-500, which brackets both; `mu_nominal` is the central case, not a measurement.
Ferrite: the bought bars are sold as "PC95" (unverified grade). TDK PC95: mu_i 3300 (25 C), Bs 530 mT (25 C) /
410 mT (100 C) at 1194 A/m (TDK PC95 material sheet; read in ferrite.py notes). The model uses mu 2500 nominal and sweeps
1000-5000: the bars are open flux paths, so L is insensitive to mu above ~1000 (checked in run_free_air.py).
"""
from __future__ import annotations

import math

MU0 = 4e-7 * math.pi
RHO_CU20, ALPHA_CU = 1.724e-8, 0.00393

SIGMA = {
    "Al5052": 1 / 4.99e-8,
    "Al1100": 1 / 2.9e-8,
    "Al3003": 1 / 4.3e-8,
    "SS304": 1 / 7.2e-7,
    "SS430": 1 / 6.0e-7,
    "steel_lowC": 1 / 1.55e-7,
    "cast_iron": 1 / 0.9e-6,
}

FERRITE_MU = 2500.0
PC95_BSAT_100C_T = 0.410
PC95_BSAT_25C_T = 0.530


def rho_cu(T):
    return RHO_CU20 * (1 + ALPHA_CU * (T - 20.0))


def skin_depth(sigma, mu_r, f):
    return 1.0 / math.sqrt(math.pi * f * MU0 * mu_r * sigma)


def frohlich(mu_lo, Js):
    """Effective (secant) permeability vs peak H for a Frohlich-Kennelly curve B = mu0 H + Js H / (H + Hk), with Hk set so
    the low-field permeability is mu_lo. ESTIMATE for large-signal runs only."""
    Hk = Js / (MU0 * (mu_lo - 1.0))

    def mu_of_H(H):
        import numpy as np
        H = np.maximum(np.asarray(H, float), 1e-3)
        return 1.0 + Js / (MU0 * (H + Hk))
    return mu_of_H


# ---- pan classes (base Ø, layers bottom-up: thickness mm, sigma, mu_r) -------------------------------------
# Thicknesses are typical of the class (ASSUMED, not a specific product).
def pan(cls, radius_mm=120.0, mu=None, rho_scale=1.0):
    """Return a pan dict for coil_model.build. mu overrides the ferromagnetic layer's permeability."""
    c = PAN_CLASSES[cls]
    layers = []
    for t, mat, mu0_ in c["layers"]:
        m_ = mu if (mu is not None and mu0_ > 1) else mu0_
        layers.append((t, SIGMA[mat] / rho_scale if mu0_ > 1 else SIGMA[mat], m_, None))
    return dict(name=cls, radius_mm=radius_mm, layers=layers)


PAN_CLASSES = {
    # magnetic (ferritic) stainless single-ply, e.g. an "induction-ready" 18/0 pan or a 430 disc base
    "ss430": dict(label="magnetic stainless (430), 1.0 mm", layers=[(1.0, "SS430", 200.0)], mu_range=(50, 500)),
    # clad tri-ply: 18/0 (430) outside, aluminium core, 18/10 (304) inside (All-Clad D3-class build-up)
    "triply": dict(label="tri-ply clad 430 0.5 / Al 1.7 / 304 0.4", layers=[(0.5, "SS430", 200.0), (1.7, "Al3003", 1.0),
                                                                          (0.4, "SS304", 1.0)], mu_range=(50, 500)),
    # cast iron skillet base
    "cast_iron": dict(label="cast iron, 4.5 mm", layers=[(4.5, "cast_iron", 100.0)], mu_range=(50, 300)),
    # enamelled / carbon steel (low-carbon steel), 2 mm
    "carbon_steel": dict(label="carbon / enamelled steel, 2.0 mm", layers=[(2.0, "steel_lowC", 200.0)], mu_range=(100, 500)),
    # aluminium pan: no heating, detect / reject case
    "aluminium": dict(label="aluminium 3003, 3.0 mm (no-heat case)", layers=[(3.0, "Al3003", 1.0)], mu_range=(1, 1)),
}
