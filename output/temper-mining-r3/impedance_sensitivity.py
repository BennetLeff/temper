"""Could the coil's reflected resistance cross-check C1's pan temperature?

Physics estimate, not a measurement. For a pan base much thicker than the skin
depth, the reflected (equivalent) resistance scales as R_eq ~ sqrt(rho * mu_eff).
Resistivity rises with temperature, rho(T) = rho20 * (1 + alpha (T - 20)); the
effective permeability of ferromagnetic bases falls with temperature, which
OPPOSES the rho effect, so ignoring mu (as here) gives an UPPER bound on the
sensitivity. alpha ranges are broad handbook-class ranges, stated per material.

Output: fractional change of R_eq per kelvin at 60/150/250 C, and the
temperature resolution implied by 0.5 % and 1 % repeatability of an R_eq = P/I^2
estimate (temper measures tank current with a CT and bus voltage with an
AMC1311; input current only if the AMC1301 lands).
R_eq is current-weighted over the heated annulus (r 20-114 mm), so it reports
the annulus, which C1 at the coil eye cannot see (sensor-r2: up to 29 K apart).
Run: python3 impedance_sensitivity.py -> impedance-sensitivity.json
"""
import json
from pathlib import Path

ALPHA = {  # 1/K, low and high ends of the assumed range
    "carbon steel (carbon-steel pan, enamelled steel)": (0.003, 0.006),
    "grey cast iron": (0.0008, 0.002),
    "ferritic stainless 430 (clad pan exterior)": (0.0008, 0.0015),
}


def main():
    rows = []
    for mat, (a_lo, a_hi) in ALPHA.items():
        for t in (60.0, 150.0, 250.0):
            s = [0.5 * a / (1 + a * (t - 20.0)) for a in (a_lo, a_hi)]   # dR/R per K
            rows.append({"material": mat, "T_C": t, "dR_over_R_pct_per_K": [round(100 * x, 3) for x in s],
                         "resolution_K_at_0p5pct": [round(0.005 / x, 1) for x in s][::-1],
                         "resolution_K_at_1pct": [round(0.01 / x, 1) for x in s][::-1]})
            r = rows[-1]
            print(f"{mat:48s} {t:5.0f} C  {r['dR_over_R_pct_per_K']} %/K  res@1% {r['resolution_K_at_1pct']} K")
    Path(__file__).with_name("impedance-sensitivity.json").write_text(
        json.dumps({"scope": __doc__.strip(), "rows": rows}, indent=1) + "\n")


if __name__ == "__main__":
    main()
