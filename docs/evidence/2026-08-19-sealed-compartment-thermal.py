#!/usr/bin/env python3
"""Sealed, gasketed PCB-compartment thermal viability -- reproducible calculation.

Companion to docs/evidence/2026-08-19-sealed-compartment-thermal-viability.md.

This script is the artifact the 2026-07-30 bound
(docs/evidence/2026-07-30-pcb-compartment-thermal-bound.md) said was "shown in
full below" but never committed.  Every input is either [repo] (cited to a
committed file) or [assumed] (an explicitly-flagged external value).  Run:

    python3 docs/evidence/2026-08-19-sealed-compartment-thermal.py

No repo state is read or written; all inputs are literals below so the output
is stable regardless of working-tree state.
"""

from __future__ import annotations

SIGMA = 5.670374419e-8  # Stefan-Boltzmann, W/m^2K^4 (CODATA, exact by definition of k_B)

# ---------------------------------------------------------------------------
# 1. UCC21550 gate-driver dissipation, per TI SLUSE89C Rev C sec. 8.2.2.5
#    (eq. 11-17).  Resolves the 1.5 W (SYSTEM_THERMAL_BUDGET.md sec. 3.4)
#    vs 0.45 W (UCC21550_Documentation.md) disagreement from primary sources.
# ---------------------------------------------------------------------------

# [repo] elec/src/modules.ato: boot cap charges to full VDD (15 V); the 5.1 V
# zener (neg_bias_zener) sets VSSA = emitter - 5.1 V, so the rail-to-rail gate
# swing VDDA-VSSA is 15 V.  TI eq. 12 note: for a split rail, VDD = positive
# rail minus negative rail.
VDD_V = 15.0
# [repo] components/IKW40N120H3/IKW40N120H3_Documentation.md line 73:
# QG = 185 nC at VCC = 960 V, IC = 40 A.  The as-built DC bus is 170 V
# (SYSTEM_THERMAL_BUDGET.md sec. 2.1), where Miller charge is substantially
# lower -- so 185 nC is CONSERVATIVE here, not nominal.
QG_C = 185e-9
# [repo] docs/hardware/RESONANT_TANK_DESIGN.md line 20: 38-50 kHz. Upper bound.
FSW_HZ = 50e3
# [repo] TI SLUSE89C sec. 5.8 lines: ROH = 5 ohm (IOUTx = -0.05 A),
# ROL = 0.55 ohm (IOUTx = 0.05 A); RNMOS = 1.47 ohm from TI eq. 5/6 worked value.
ROH, ROL, RNMOS = 5.0, 0.55, 1.47
# [repo] elec/src/modules.ato line 160 (GateDriveHS) and line 218
# (GateDriveLS): rg_on = 2.2 ohm, both channels.  There is NO separate
# turn-off resistor or diode bypass in either module -- turn-off returns
# through the same 2.2 ohm.  TI's own example used ROFF = 0; this board's
# lack of a turn-off bypass keeps MORE loss out of the driver, not less.
RON_OHM = 2.2
ROFF_PARALLEL_RON_OHM = RON_OHM  # no bypass path exists on this board

# TI SLUSE89C eq. 11.  [repo] sec. 5.8: IVCC 4.2 typ / 4.8 max mA (VCC = 5 V);
# IVDDx 1.5 typ / 2.5 max mA (VDD = 25 V).  VCCI on this board is the 3.3 V
# rail (elec/src/modules.ato: c_vcci1 ties to power_3v3.vcc; sec. 252 comment
# "VCCI is the 3.0-5.5 V control-side supply").  Datasheet MAXIMA used.
VCCI_V, IVCCI_A = 3.3, 4.8e-3
IVDDA_A = IVDDB_A = 2.5e-3


def ucc21550_pgd(rg_int_ohm: float) -> tuple[float, float, float]:
    """Return (PGDQ, PGDO, PGD) in W for a given IGBT internal gate resistance."""
    pgdq = VCCI_V * IVCCI_A + VDD_V * IVDDA_A + VDD_V * IVDDB_A      # eq. 11
    pgsw = 2.0 * VDD_V * QG_C * FSW_HZ                                # eq. 12
    roh_par = (ROH * RNMOS) / (ROH + RNMOS)                           # ROH || RNMOS
    frac_up = roh_par / (roh_par + RON_OHM + rg_int_ohm)
    frac_dn = ROL / (ROL + ROFF_PARALLEL_RON_OHM + rg_int_ohm)
    pgdo = (pgsw / 2.0) * (frac_up + frac_dn)                         # eq. 14
    return pgdq, pgdo, pgdq + pgdo                                    # eq. 17


# ---------------------------------------------------------------------------
# 2. Sealed-enclosure steady-state balance.  Same closure as the 2026-07-30
#    bound so the two are directly comparable, re-run at the committed 60 C
#    ambient (packages/temper-thermal/src/thermal_constants.rs DEFAULT_AMBIENT_C,
#    set by docs/evidence/2026-08-15-thermal-threshold-decision.md sec. 6.4).
# ---------------------------------------------------------------------------
#
# [assumed/external] h = 1.42*(dT/Lc)^0.25 W/m^2K -- simplified free-convection
# correlation for an isothermal surface in still air.  NOT a repo figure and
# NOT independently validated; carried unchanged from the 2026-07-30 bound so
# that this document's conclusion can be compared against it like-for-like.


def wall_delta_t(q_w: float, area_m2: float, lc_m: float, emissivity: float,
                 ta_c: float) -> float:
    """Solve Q = h*A*dT + eps*sigma*A*(Ts^4 - Ta^4) for dT by bisection."""
    ta_k = ta_c + 273.15

    def residual(dt: float) -> float:
        h = 1.42 * (dt / lc_m) ** 0.25
        ts_k = ta_k + dt
        return h * area_m2 * dt + emissivity * SIGMA * area_m2 * (ts_k**4 - ta_k**4) - q_w

    lo, hi = 1e-6, 500.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if residual(mid) < 0.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)



# ---------------------------------------------------------------------------
# 2b. LMR51430 buck dissipation at the AS-BUILT operating point.
#     docs/hardware/LMR51430_THERMAL_ANALYSIS.md derives its 1.0 W from
#     VOUT = 5.0 V, IOUT = 1.2 A (= 6.0 W out).  That is NOT this board:
#     elec/src/modules.ato BuckConverter3V3 sets power_out.voltage = 3.3V and
#     uses TI Table 9-1 for Vout=3.3V/500kHz; the 3.3 V rail load is 254 mA
#     (docs/hardware/COMPONENT_COMPATIBILITY_VERIFICATION.md line 65:
#     ESP32-S3 150 + MAX31865 2 + ADUM1250 2 + misc 100 mA), with ~380 mA
#     carried as the conservative figure from the same table.
# ---------------------------------------------------------------------------
VIN_BUCK_V, VOUT_BUCK_V = 15.0, 3.3          # [repo] modules.ato PowerManagement
RDSON_HS, RDSON_LS = 0.12, 0.07              # [repo] LMR51430 DS sec. 7.5, TJ=25C
FSW_BUCK_HZ = 500e3                          # [repo] modules.ato TI Table 9-1


def buck_ic_loss(iout_a: float, eta: float, hot_factor: float = 1.5) -> tuple[float, float]:
    """Return (loss_by_efficiency_total, loss_conduction_only) in W."""
    pout = VOUT_BUCK_V * iout_a
    total = pout * (1.0 / eta - 1.0)          # includes inductor + caps, not just IC
    duty = VOUT_BUCK_V / VIN_BUCK_V
    cond = iout_a**2 * hot_factor * (duty * RDSON_HS + (1.0 - duty) * RDSON_LS)
    return total, cond


# [assumed] Compact envelope from the 2026-07-30 bound sec. 1.1: board
# 152 x 234 mm (Edge.Cuts, measured) + 8 mm standoff + 25 mm clearance.
COMPACT = dict(area_m2=0.0966, lc_m=0.234, label="compact 152x234x33 mm")
GENEROUS = dict(area_m2=0.1300, lc_m=0.254, label="generous 172x254x50 mm")


def main() -> None:
    print("=" * 78)
    print("1. UCC21550 gate-driver dissipation (TI SLUSE89C sec. 8.2.2.5)")
    print("=" * 78)
    pgsw = 2.0 * VDD_V * QG_C * FSW_HZ
    print(f"  PGSW (total gate-loop loss, both channels) = {pgsw*1e3:6.1f} mW")
    print("  -- only the fraction dropped across the driver's own pull-up/")
    print("     pull-down stays in the package (TI eq. 14):")
    print()
    print(f"  {'RG_int (IGBT)':>16} | {'PGDQ':>8} | {'PGDO':>8} | {'PGD total':>10}")
    print(f"  {'-'*16}-+-{'-'*8}-+-{'-'*8}-+-{'-'*10}")
    for rg_int, note in [
        (4.6, "TI worked-example value"),
        (0.0, "worst case: no internal RG"),
    ]:
        pgdq, pgdo, pgd = ucc21550_pgd(rg_int)
        print(f"  {rg_int:>13.1f} oh | {pgdq*1e3:6.1f} mW | {pgdo*1e3:6.1f} mW "
              f"| {pgd*1e3:7.1f} mW   ({note})")
    # Absolute ceiling: every joule of gate loss trapped in the package.
    pgdq, _, _ = ucc21550_pgd(4.6)
    print(f"  {'(ceiling)':>13}    | {pgdq*1e3:6.1f} mW | {pgsw*1e3:6.1f} mW "
          f"| {(pgdq+pgsw)*1e3:7.1f} mW   (RON=RG_int=0, physically impossible)")
    print()
    print(f"  Datasheet sec. 5.5 absolute-max PD (both sides) = 950.0 mW")
    print(f"  -> the 1.5 W figure in SYSTEM_THERMAL_BUDGET.md sec. 3.4 EXCEEDS the")
    print(f"     part's own absolute-maximum dissipation rating by 58%.")
    print()

    print("=" * 78)
    print("2. Sealed-compartment wall rise at the committed 60 C ambient")
    print("=" * 78)
    for geom in (COMPACT, GENEROUS):
        print(f"\n  Geometry: {geom['label']}  (A = {geom['area_m2']*1e4:.0f} cm^2)")
        print(f"  {'Q (W)':>6} | {'eps=0.2':>9} | {'eps=0.5':>9} | {'eps=0.9':>9}")
        print(f"  {'-'*6}-+-{'-'*9}-+-{'-'*9}-+-{'-'*9}")
        for q in (9.65, 12.0):
            cells = []
            for eps in (0.2, 0.5, 0.9):
                dt = wall_delta_t(q, geom["area_m2"], geom["lc_m"], eps, 60.0)
                cells.append(f"{dt:6.1f} C")
            print(f"  {q:>6.2f} | {cells[0]:>9} | {cells[1]:>9} | {cells[2]:>9}")
    print()

    print("=" * 78)
    print("3. Per-part junction margin, sealed compartment, Ta = 60 C")
    print("=" * 78)
    # Worst credible local ambient: compact geometry, Q = 12 W, eps = 0.2,
    # times the 2026-07-30 bound's x1.3 internal-film factor [assumed].
    dt_worst = wall_delta_t(12.0, COMPACT["area_m2"], COMPACT["lc_m"], 0.2, 60.0)
    local_worst = 60.0 + 1.3 * dt_worst
    dt_central = wall_delta_t(9.65, COMPACT["area_m2"], COMPACT["lc_m"], 0.5, 60.0)
    local_central = 60.0 + 1.3 * dt_central
    print(f"  Local ambient, central  (Q=9.65 W, eps=0.5, x1.3) = {local_central:5.1f} C")
    print(f"  Local ambient, worst    (Q=12.0 W, eps=0.2, x1.3) = {local_worst:5.1f} C")
    print()

    _, _, pgd = ucc21550_pgd(4.6)
    _, _, pgd_wc = ucc21550_pgd(0.0)
    parts = [
        # (name, P_W, theta_JA, Tj_max, source note)
        ("UCC21550 (as-built P)",   pgd,    74.1, 150.0, "DS 5.4 DWK; P per 5.5/8.2.2.5"),
        ("UCC21550 (RG_int=0)",     pgd_wc, 74.1, 150.0, "worst-case split"),
        ("UCC21550 (stale 1.5 W)",  1.5,    74.1, 150.0, "SYSTEM_THERMAL_BUDGET 3.4"),
        ("LMR51430 (as-built P)",   0.20,  107.8, 150.0, "3.3 V @ 380 mA, DS 7.4 JEDEC"),
        ("LMR51430 (stale 1.0 W)",  1.00,   80.0, 150.0, "LMR51430_THERMAL_ANALYSIS"),
    ]
    print(f"  {'Part':<24} | {'P (W)':>6} | {'thJA':>6} | {'Tj worst':>9} | {'margin':>8}")
    print(f"  {'-'*24}-+-{'-'*6}-+-{'-'*6}-+-{'-'*9}-+-{'-'*8}")
    for name, p, tja, tjmax, _note in parts:
        tj = local_worst + p * tja
        print(f"  {name:<24} | {p:>6.3f} | {tja:>6.1f} | {tj:>7.1f} C | "
              f"{tjmax - tj:>+6.1f} C")
    print()
    print("  (Tj computed at the WORST local ambient above; the central case is")
    print(f"   {local_worst - local_central:.1f} C cooler still.)")
    print()

    print("=" * 78)
    print("4. Robustness: dissipation at which each part reaches Tj(max)=150 C")
    print("=" * 78)
    print(f"  Evaluated at the WORST local ambient ({local_worst:.1f} C): compact")
    print("  geometry, Q = 12 W, emissivity 0.2, x1.3 internal-film factor --")
    print("  i.e. every unfavourable assumption in the sweep stacked at once.")
    print()
    for name, tja, p_actual in [
        ("UCC21550 (74.1 C/W)", 74.1, ucc21550_pgd(4.6)[2]),
        ("LMR51430 (107.8 C/W)", 107.8, 0.20),
    ]:
        p_break = (150.0 - local_worst) / tja
        print(f"  {name:<22} breakeven P = {p_break*1e3:6.1f} mW  "
              f"vs as-built {p_actual*1e3:6.1f} mW  -> {p_break/p_actual:4.1f}x headroom")
    print()
    print("  Buck loss cross-check at the as-built operating point")
    print("  (15 V -> 3.3 V; the analysis doc's 1.0 W assumes 5.0 V @ 1.2 A):")
    for iout, eta in ((0.254, 0.85), (0.380, 0.85), (0.380, 0.75)):
        total, cond = buck_ic_loss(iout, eta)
        print(f"    IOUT={iout*1e3:5.1f} mA, eta={eta:.2f} -> system loss {total*1e3:5.1f} mW "
              f"(conduction alone {cond*1e3:4.1f} mW)")



if __name__ == "__main__":
    main()
