"""Dry-air properties for the jet bench (imported by plate_design.py, setpoints.py, fit.py).

Sutherland's law for viscosity and conductivity (White, Viscous Fluid Flow, Table 1-2/1-3 constants), ideal gas
density, constant cp. At 50 C these give rho 1.093, nu 1.79e-5, k 0.0280; delivery.py uses 1.09 / 1.8e-5 / 0.0285
(coil_thermal's set), so the two agree within 2 % on k and 1 % elsewhere.
"""
from __future__ import annotations

R_AIR, CP_AIR, P_ATM = 287.05, 1006.0, 101325.0
SIGMA = 5.670374e-8


def props(t_c: float, p_pa: float = P_ATM) -> dict:
    t = t_c + 273.15
    mu = 1.716e-5 * (t / 273.15) ** 1.5 * (273.15 + 110.4) / (t + 110.4)
    k = 0.0241 * (t / 273.15) ** 1.5 * (273.15 + 194.0) / (t + 194.0)
    rho = p_pa / (R_AIR * t)
    return {"T_C": t_c, "rho": rho, "mu": mu, "nu": mu / rho, "k": k, "cp": CP_AIR, "Pr": mu * CP_AIR / k}
