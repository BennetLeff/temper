#!/usr/bin/env python3
"""Decision table: what output rating is actually available on each supply.

provenance: commit=610d09cf165a5d9128017a7018ff56ec6c8169bd dirty=false
    (branch analysis/output-rating-decision, cut from origin/main
    eb5022510d8f1272adf0a27d76c849aa2bb6e210, with fe9cf6752 --
    docs/evidence/2026-08-19-input-stage-power-ceiling.{md,py} -- cherry-picked
    as the input this builds on).
    pcb/temper.kicad_pcb sha256=26981fea2dbc425f456010d4d4e755cdebdefee2b535
    5ad915086352b90c110b -- verified before and after; never opened for writing.

WHAT THIS ANSWERS
    "For each candidate supply scenario, what is the maximum deliverable output
    power (a) as the design stands, (b) with the bus-capacitor and HF-bypass
    defects fixed, (c) with PFC added -- and what is the binding constraint in
    every one of those cells?"

    The prior analysis (fe9cf6752) answered this for one supply only:
    120 V / 15 A / 60 Hz, Delon doubler.  This generalises it.

METHOD
    Reuses the prior script's time-domain rectifier simulation unchanged for
    the doubler, and adds a full-wave BRIDGE model for the >=200 V scenarios.
    The bridge is not an option there, it is a requirement: a Delon doubler on
    240 V produces a ~680 V bus, which no part in this BOM survives (bus caps
    are 250 V, main.ato:601 asserts v_bus_max <= 400V).  On a bridge the same
    two series capacitor banks see the same ~340 V bus they see today, which is
    why the DC-side BOM is even a candidate for survival.

    Every rating is turned into an output-power ceiling on a shared
    geometric power grid (one simulation sweep serves all constraints and
    both tank variants), with the crossing log-interpolated.  The prior
    script bisected per constraint; the two agree -- sec.H.3 reproduces its
    120 V/15 A operating point to within 0.04 %.

    IMPORTANT STRUCTURAL FACT, and the reason column (a) barely moves:
    the 47 kHz tank current is set by the RESONANT TANK and the reflected pan
    impedance, not by the line.  It is the same current at the same output
    power on every supply.  So the HF ripple term landing on the electrolytics
    is supply-INDEPENDENT.  Changing the mains cannot move column (a) more
    than the LF term allows.

PROVENANCE TAGS -- never blended:
    [datasheet]     printed in a manufacturer document, read this session or by
                    the prior derivation and quoted with a verification date
    [repo]          a committed value in this repository
    [derived]       computed here from [datasheet]/[repo] inputs only
    [estimated]     not published anywhere reachable; a bracket, not a value
    [standard]      quoted from a code/standard text located this session,
                    with the section number
    [UNOBTAINABLE]  named and left unquantified
    [market]        commercial-product context.  NEVER an engineering input.

RUNTIME
    Pure stdlib except that it imports the prior committed evidence script from
    the same directory for its inputs.  Reads no other repo state, writes no
    files, touches no board file.  ``make venv-isolate`` is therefore NOT
    required to reproduce this -- stated explicitly per the task's rule.

    python3 docs/evidence/2026-08-19-output-rating-decision-table.py
"""

from __future__ import annotations

import importlib.util
import math
import os
import sys
from dataclasses import dataclass

# --- import the prior committed derivation as the input to this one ----------
_HERE = os.path.dirname(os.path.abspath(__file__))
_PRIOR = os.path.join(_HERE, "2026-08-19-input-stage-power-ceiling.py")
_spec = importlib.util.spec_from_file_location("_prior", _PRIOR)
assert _spec is not None and _spec.loader is not None
P = importlib.util.module_from_spec(_spec)
sys.modules["_prior"] = P            # dataclasses needs the module registered
_spec.loader.exec_module(P)          # noqa: E402  (the module only defines)


# =============================================================================
# 1. SUPPLY SCENARIOS
# =============================================================================

@dataclass
class Supply:
    key: str
    v_rms: float
    f_hz: float
    i_branch: float           # branch / OCPD ampere rating
    topology: str             # "doubler" | "bridge"
    plug: str
    region: str               # "NA" (NEC applies) | "IEC"
    note: str = ""

    @property
    def va(self) -> float:
        return self.v_rms * self.i_branch

    @property
    def i_cont(self) -> float | None:
        """80 % of the branch rating -- NEC only.  None where NEC does not
        apply; the IEC world has no equivalent blanket 80 % rule and none is
        invented here."""
        return 0.8 * self.i_branch if self.region == "NA" else None


# Topology assignment is forced, not chosen:
#   <=130 V  -> doubler, because a bridge would give a ~170 V bus and the
#              1200 V IGBT half-bridge / 47 kHz tank / ZVS design is built
#              around 340 V (main.ato:49,65).
#   >=200 V  -> bridge, because a doubler would give 600-680 V and
#              main.ato:601 `assert v_bus_max <= 400V` plus the 250 V bus
#              capacitors forbid it.
SUPPLIES = [
    Supply("120V/15A", 120.0, 60.0, 15.0, "doubler", "NEMA 5-15P", "NA",
           "AS DECLARED.  main.ato:52 v_ac_nominal=120V, :56 asserts "
           "100-130V 'NEMA 5-15 tolerance', :62 f_line=60Hz, "
           "constraints.ato:12 i_max=15A."),
    Supply("120V/20A", 120.0, 60.0, 20.0, "doubler", "NEMA 5-20P", "NA",
           "Same appliance, 20 A branch.  A 5-20P will NOT enter a 5-15R, so "
           "this is a different installed base, not a superset."),
    Supply("240V/15A", 240.0, 60.0, 15.0, "bridge", "NEMA 6-15P", "NA",
           "NA split-phase, two ungrounded conductors, NO neutral."),
    Supply("240V/20A", 240.0, 60.0, 20.0, "bridge", "NEMA 6-20P", "NA",
           "NA split-phase.  The current the task asked to be stated: 20 A."),
    Supply("240V/30A", 240.0, 60.0, 30.0, "bridge", "NEMA 6-30P", "NA",
           "NA split-phase, hard-wire or 6-30 range-class receptacle."),
    Supply("230V/16A", 230.0, 50.0, 16.0, "bridge", "CEE 7/7 (Schuko)", "IEC",
           "Continental EU.  50 Hz is worse for LF ripple than 60 Hz."),
    Supply("230V/13A", 230.0, 50.0, 13.0, "bridge", "BS 1363", "IEC",
           "UK.  The 13 A fused plug is the binding element, not the 32 A "
           "ring final."),
]

# PF assumed for a PFC front end.  0.95 is the value the prior derivation used
# and is a conservative floor for a boost PFC; a good one reaches 0.99.
PF_PFC = 0.95
# A second, deliberately optimistic PFC point, reported separately and NEVER
# blended into the 0.95 column.
PF_PFC_BEST = 0.99


# =============================================================================
# 1b. TANK CURRENT AT 1800 W -- A CORRECTION TO THE INPUT DERIVATION
# =============================================================================
# fe9cf6752 took I_tank(1800 W) = 35.4-40.0 A from
# docs/evidence/2026-07-26-ocp01-vs-full-power-current.md.  That document is
# SUPERSEDED in-tree.  docs/evidence/2026-08-15-ocp-threshold-decision.md sec.2
# states, verbatim: "The interlocks audit's current-band numbers (35.4 A RMS /
# 50.0 A peak at R_eff = 1.44 ohm, 56.6 A peak at R_eff = 1.12 ohm) come from
# the PRE-COIL-SPEC state of the repo.  The coil is now specified", and gives
#     1800 W tank current = 22.5 A rms / 31.9 A peak  (first-harmonic solve,
#     R_eff 3.55 ohm @ 46.6 kHz); ngspice harness 20.7 A rms / 28.7 A peak.
# The same table marks the 1.12 ohm / 40 A figure "UNCITED, not corroborated".
# 22.5 A is also the number committed in elec/src/modules.ato:585-593.
#
# 35.4 A is separately recognisable as main.ato:625 `i_ocp_trip_rms = 35.4A`,
# i.e. the OCP TRIP LEVEL, not an operating current.
#
# BOTH are carried below and reported SEPARATELY.  They are never blended and
# neither is averaged into the other.
TANK_VARIANTS = {
    "committed": (20.7, 22.5),    # [repo] 2026-08-15-ocp-threshold-decision.md
                                  # sec.2 + modules.ato:585-593.  PRIMARY.
    "superseded": (35.4, 40.0),   # [repo, SUPERSEDED] 2026-07-26 doc, as used
                                  # by fe9cf6752.  Sensitivity only.
}


def cases_for(tank: str) -> list:
    """The prior script's three bracket cases, re-pointed at a tank bracket."""
    lo, hi = TANK_VARIANTS[tank]
    mid = 0.5 * (lo + hi)
    out = []
    for c, it in zip(P.CASES, (lo, mid, hi), strict=True):
        out.append(P.Case(c.name, c.eta, c.rs, c.vf0, c.rd, it, c.note))
    return out


# =============================================================================
# 2. GENERALISED RECTIFIER SIMULATION
# =============================================================================
#
# PERFORMANCE NOTE (does not affect any result): the spectral step below
# handles harmonics 1..H_EXACT exactly and lumps everything above into one
# residual bucket, using Parseval.  That is legitimate because the KMQ
# frequency-multiplier table SATURATES (P.CAP_FM_TABLE tops out at 1.50 by
# 50 kHz and is already 1.45 at 10 kHz), so every harmonic in the tail gets
# essentially the same divisor.  The residual is divided by the multiplier at
# the LOWEST tail frequency, which is the SMALLEST divisor in the tail and
# therefore the LARGEST equivalent current -- the approximation is
# conservative, never optimistic.  Sec.H checks it against the exact
# harmonic-by-harmonic sum.

H_EXACT = 25            # harmonics resolved individually
N_DFT = 1000            # samples used for the spectral step
_BASIS: dict[int, list[tuple[list[float], list[float]]]] = {}


def _basis(n: int):
    b = _BASIS.get(n)
    if b is None:
        b = []
        for h in range(1, H_EXACT + 1):
            w = 2.0 * math.pi * h / n
            b.append(([math.cos(w * k) for k in range(n)],
                      [math.sin(w * k) for k in range(n)]))
        _BASIS[n] = b
    return b


@dataclass
class Op2:
    p_out: float
    p_in: float
    i_line_rms: float
    i_line_pk: float
    pf: float
    theta_deg: float
    v_bus_avg: float
    v_bus_pp: float
    v_half_avg: float
    i_diode_pk: float
    i_diode_avg: float
    i_cap_unit_lf_eq: float      # per capacitor, 120 Hz-equivalent, LF only


def _lf_equivalent(i_cap: list[float], f_line: float, exact: bool = False
                   ) -> float:
    """Per-BANK 120 Hz-equivalent rms of the LF capacitor current."""
    n0 = len(i_cap)
    if exact:
        eq2 = 0.0
        for h in range(1, 101):
            re = im = 0.0
            w = 2.0 * math.pi * h / n0
            for k in range(n0):
                ang = w * k
                re += i_cap[k] * math.cos(ang)
                im += i_cap[k] * math.sin(ang)
            amp = 2.0 / n0 * math.hypot(re, im)
            eq2 += (amp / math.sqrt(2.0) / P.cap_freq_multiplier(h * f_line)) ** 2
        return math.sqrt(eq2)

    step = max(1, n0 // N_DFT)
    x = i_cap[::step]
    n = len(x)
    dc = sum(x) / n
    tot2 = sum(v * v for v in x) / n - dc * dc      # total AC power
    eq2 = 0.0
    acc2 = 0.0
    for h, (cs, sn) in enumerate(_basis(n), start=1):
        re = im = 0.0
        for k in range(n):
            re += x[k] * cs[k]
            im += x[k] * sn[k]
        amp = 2.0 / n * math.hypot(re, im)
        rms_h2 = amp * amp / 2.0
        acc2 += rms_h2
        eq2 += rms_h2 / P.cap_freq_multiplier(h * f_line) ** 2
    tail2 = max(0.0, tot2 - acc2)
    eq2 += tail2 / P.cap_freq_multiplier((H_EXACT + 1) * f_line) ** 2
    return math.sqrt(eq2)


# The simulation is INDEPENDENT of the tank current, so one cache serves every
# tank variant.  Key: (supply, case-name, p_in, c_half, resolution).
_SIM_CACHE: dict[tuple, Op2] = {}


def simulate_gen(sup: Supply, p_in: float, rs: float, vf0: float, rd: float,
                 c_half: float = P.C_HALF, n_per_cycle: int = 2000,
                 n_cycles: int = 30, exact_dft: bool = False) -> Op2:
    """Time-domain rectifier, constant-power load, forward Euler.

    topology == "doubler":  identical to the prior script's `simulate`.
        Two banks of c_half each, one recharged per line cycle by one diode.
    topology == "bridge":   full-wave bridge into the SAME two banks, now in
        series across the whole bus, i.e. an effective c_half/2.  Two diodes
        conduct in series each half-cycle (2*vf0, 2*rd), and the bus recharges
        TWICE per line cycle.  Every series element carries the same current,
        so each bank -- and each capacitor in it -- sees the full bus ripple.
    """
    key = (sup.key, round(p_in, 4), round(rs, 6), round(vf0, 4), round(rd, 6),
           c_half, n_per_cycle, n_cycles, exact_dft)
    hit = _SIM_CACHE.get(key)
    if hit is not None:
        return hit

    v_pk = sup.v_rms * math.sqrt(2.0)
    t_line = 1.0 / sup.f_hz
    omega = 2.0 * math.pi * sup.f_hz
    dt = t_line / n_per_cycle

    if sup.topology == "doubler":
        n_series_d = 1
        c_eff = c_half                     # per half-bus
        v_target = v_pk - vf0              # per half-bus
    else:
        n_series_d = 2
        c_eff = c_half / 2.0               # two banks in series
        v_target = v_pk - 2.0 * vf0        # whole bus

    r_series = rs + n_series_d * rd
    vf_tot = n_series_d * vf0

    if sup.topology == "doubler":
        droop0 = (p_in / 2.0) / max(v_target, 1.0) * t_line / c_eff
        v1 = max(v_target - droop0, 20.0)
        v2 = v1
    else:
        droop0 = p_in / max(v_target, 1.0) * (t_line / 2.0) / c_eff
        vb = max(v_target - droop0, 20.0)

    i_line = i_rect = i_d_one = v_src_s = v_bus_s = i_cap_s = []
    for cyc in range(n_cycles):
        record = cyc == n_cycles - 1
        if record:
            i_line = [0.0] * n_per_cycle
            i_rect = [0.0] * n_per_cycle
            i_d_one = [0.0] * n_per_cycle
            v_src_s = [0.0] * n_per_cycle
            v_bus_s = [0.0] * n_per_cycle
            i_cap_s = [0.0] * n_per_cycle
        for k in range(n_per_cycle):
            vs = v_pk * math.sin(omega * (k * dt))

            if sup.topology == "doubler":
                id1 = id2 = 0.0
                drive1 = vs - vf_tot - v1
                if drive1 > 0.0:
                    id1 = drive1 / r_series
                else:
                    drive2 = -vs - vf_tot - v2
                    if drive2 > 0.0:
                        id2 = drive2 / r_series
                il1 = (p_in / 2.0) / (v1 if v1 > 1.0 else 1.0)
                il2 = (p_in / 2.0) / (v2 if v2 > 1.0 else 1.0)
                v1 += (id1 - il1) / c_eff * dt
                v2 += (id2 - il2) / c_eff * dt
                if v1 < 1.0:
                    v1 = 1.0
                if v2 < 1.0:
                    v2 = 1.0
                if record:
                    i_line[k] = id1 - id2
                    i_rect[k] = id1
                    i_d_one[k] = id1              # D1 alone
                    v_src_s[k] = vs
                    v_bus_s[k] = v1 + v2
                    i_cap_s[k] = id1 - il1        # upper bank
            else:
                drive = (vs if vs >= 0.0 else -vs) - vf_tot - vb
                ir = drive / r_series if drive > 0.0 else 0.0
                il = p_in / (vb if vb > 1.0 else 1.0)
                vb += (ir - il) / c_eff * dt
                if vb < 1.0:
                    vb = 1.0
                if record:
                    i_line[k] = ir if vs >= 0.0 else -ir
                    i_rect[k] = ir
                    # each of the 4 bridge diodes conducts on ONE half-cycle
                    i_d_one[k] = ir if vs >= 0.0 else 0.0
                    v_src_s[k] = vs
                    v_bus_s[k] = vb
                    i_cap_s[k] = ir - il          # series stack current

    n = n_per_cycle
    i_line_rms = math.sqrt(sum(x * x for x in i_line) / n)
    i_line_pk = max(abs(x) for x in i_line)
    p_real = sum(v_src_s[k] * i_line[k] for k in range(n)) / n
    pf = p_real / (sup.v_rms * i_line_rms) if i_line_rms > 0 else 0.0

    n_cond = sum(1 for x in i_rect if x > 0.0)
    # conduction angle of ONE diode: doubler = one pulse/cycle, bridge = two
    theta_deg = 360.0 * n_cond / n / (1 if sup.topology == "doubler" else 2)

    v_bus_avg = sum(v_bus_s) / n
    v_bus_pp = max(v_bus_s) - min(v_bus_s)

    op = Op2(p_out=float("nan"), p_in=p_in, i_line_rms=i_line_rms,
             i_line_pk=i_line_pk, pf=pf, theta_deg=theta_deg,
             v_bus_avg=v_bus_avg, v_bus_pp=v_bus_pp,
             v_half_avg=v_bus_avg / 2.0,
             i_diode_pk=max(i_d_one), i_diode_avg=sum(i_d_one) / n,
             i_cap_unit_lf_eq=_lf_equivalent(i_cap_s, sup.f_hz, exact_dft)
             / P.N_PARALLEL)
    _SIM_CACHE[key] = op
    return op


# =============================================================================
# 3. CEILINGS
# =============================================================================

def op_at(sup: Supply, case, p_out: float, **kw) -> Op2:
    op = simulate_gen(sup, p_out / case.eta, case.rs, case.vf0, case.rd, **kw)
    op.p_out = p_out
    return op


def cap_total(op: Op2, case, p_out: float,
              tank_scaling: str = "sqrt") -> float:
    """Per-capacitor 120 Hz-equivalent ripple, LF (+) HF in quadrature.

    The HF term is IDENTICAL to the prior script's and is SUPPLY-INDEPENDENT:
    the tank current at a given output power is set by the resonant tank and
    the reflected pan resistance, not by the mains.
    """
    if tank_scaling == "sqrt":
        scale = math.sqrt(max(p_out, 0.0) / P.P_OUT_DECLARED)
    else:
        scale = max(p_out, 0.0) / P.P_OUT_DECLARED
    hf_eq = P.CAP_HF_SHARE * case.i_tank_1800 * scale / P.FM_SW
    return math.hypot(op.i_cap_unit_lf_eq, hf_eq)


# A shared geometric power grid.  Every metric is evaluated on the SAME grid,
# so one simulation sweep serves all constraints and both tank variants.
P_LO, P_HI, N_GRID = 20.0, 6000.0, 60
P_GRID = [P_LO * (P_HI / P_LO) ** (i / (N_GRID - 1)) for i in range(N_GRID)]


def sweep(sup: Supply, case) -> list[Op2]:
    return [op_at(sup, case, p) for p in P_GRID]


def crossing(ops: list[Op2], metric, limit: float) -> float:
    """Output power at which `metric` first reaches `limit`, log-interpolated
    on the shared grid.  Monotone metrics only (all of these are)."""
    vals = [metric(o, o.p_out) for o in ops]
    if vals[0] >= limit:
        return 0.0
    for a in range(1, len(vals)):
        if vals[a] >= limit:
            x0, x1 = math.log(ops[a - 1].p_out), math.log(ops[a].p_out)
            y0, y1 = vals[a - 1], vals[a]
            if y1 == y0:
                return ops[a].p_out
            return math.exp(x0 + (limit - y0) / (y1 - y0) * (x1 - x0))
    return float("inf")


def bracket(vals: list[float]) -> tuple[float, float]:
    fin = [v for v in vals if math.isfinite(v)]
    if not fin:
        return (float("inf"), float("inf"))
    return (min(fin), max(fin))


def fmt(x: float) -> str:
    if x == float("inf"):
        return ">6000"
    if x == 0.0:
        return "0"
    return f"{x:.0f}"


def fmt_br(b: tuple[float, float]) -> str:
    lo, hi = b
    if lo == float("inf"):
        return ">6000 W"
    if abs(hi - lo) < 2.0:
        return f"{fmt(lo)} W"
    return f"{fmt(lo)}-{fmt(hi)} W"


# --- PFC ceilings are closed-form: sinusoidal current --------------------
def pfc_ceiling(sup: Supply, eta: float, i_limit: float,
                pf: float = PF_PFC) -> float:
    return sup.v_rms * i_limit * pf * eta


# =============================================================================
# 4. REPORT
# =============================================================================

def hr(c: str = "=") -> None:
    print(c * 102)


def build(sup: Supply, cases: list) -> dict:
    """All rating ceilings, per bracket case, for one supply."""
    per_case = {}
    for c in cases:
        ops = sweep(sup, c)
        lim = {}
        lim["C_BUS x4 ripple 2.70A"] = crossing(
            ops, lambda o, p, c=c: cap_total(o, c, p), P.CAP_I_RIPPLE_RATED)
        lim["D I_FRM 30A peak"] = crossing(
            ops, lambda o, p: o.i_diode_pk, P.D_IFRM)
        lim[f"branch {sup.i_branch:.0f}A"] = crossing(
            ops, lambda o, p: o.i_line_rms, sup.i_branch)
        lim[f"F1/L1 {P.I_FUSE_RATED:.0f}A"] = crossing(
            ops, lambda o, p: o.i_line_rms, P.I_FUSE_RATED)
        lim[f"K1 IEC {P.I_K1_IEC:.0f}A"] = crossing(
            ops, lambda o, p: o.i_line_rms, P.I_K1_IEC)
        lim[f"K1 UL508 {P.I_K1_UL:.0f}A"] = crossing(
            ops, lambda o, p: o.i_line_rms, P.I_K1_UL)
        if sup.i_cont is not None:
            lim[f"NEC-80% {sup.i_cont:.0f}A"] = crossing(
                ops, lambda o, p: o.i_line_rms, sup.i_cont)
        per_case[c.name] = lim
    return per_case


def col(per_case: dict, cases: list, drop_prefixes: tuple):
    """Min ceiling over the surviving constraints, bracketed across cases."""
    vals, names = [], []
    for c in cases:
        sub = {k: v for k, v in per_case[c.name].items()
               if not k.startswith(drop_prefixes)}
        k = min(sub, key=lambda kk: sub[kk])
        vals.append(sub[k])
        names.append(k)
    uniq = names[0] if len(set(names)) == 1 else " | ".join(names)
    return bracket(vals), uniq


# Constraints excluded from every headline column:
#   NEC-80%  -- carried separately (sec.E.1); it is an INSTALLATION rule on
#               the branch circuit, not a component rating.
#   K1 UL508 -- K1's higher of two ratings; the IEC one governs a 60335
#               product, so the IEC one is the headline.
DROP_HEADLINE = ("NEC-80%", "K1 UL508")


def main() -> None:
    print(__doc__.strip().splitlines()[0])
    hr()
    print(f"Bus caps: {P.N_PARALLEL} x {P.C_UNIT*1e6:.0f} uF per half, "
          f"{P.CAP_I_RIPPLE_RATED} Arms @105C/120Hz, {P.CAP_V_RATED:.0f} Vdc "
          "[datasheet]")
    print(f"D1/D2 MUR1560 I_FRM = {P.D_IFRM:.0f} A repetitive peak [datasheet]")
    print(f"F1 / L1 = {P.I_FUSE_RATED:.0f} A ; K1 = {P.I_K1_IEC:.0f} A IEC / "
          f"{P.I_K1_UL:.0f} A UL508 [repo]/[datasheet]")
    print(f"HF share {P.CAP_HF_SHARE} x I_tank ; FM({P.F_SW/1e3:.0f}kHz) = "
          f"{P.FM_SW:.2f} [repo]/[datasheet]")
    print(f"PFC PF = {PF_PFC} (and {PF_PFC_BEST} separately, never blended)")
    print()
    for k, v in TANK_VARIANTS.items():
        print(f"  tank variant '{k}': I_tank(1800W) = {v[0]}-{v[1]} A rms")
    print()

    for tank in ("committed", "superseded"):
        cases = cases_for(tank)
        lo, hi = TANK_VARIANTS[tank]
        hr()
        label = ("PRIMARY -- the committed operating point"
                 if tank == "committed"
                 else "SENSITIVITY ONLY -- the SUPERSEDED figure fe9cf6752 used")
        print(f"TANK VARIANT '{tank}'  ({lo}-{hi} A rms at 1800 W)")
        print(f"    {label}")
        hr()

        # ------------------------------------------------------------ A
        print("\nA.  SUPPLY-INDEPENDENCE OF THE HF TERM")
        hr("-")
        hf = [P.CAP_HF_SHARE * c.i_tank_1800 / P.FM_SW for c in cases]
        print(f"    HF/cap at 1800 W: {min(hf):.2f}-{max(hf):.2f} A eq  "
              f"({min(hf)/P.CAP_I_RIPPLE_RATED:.2f}-"
              f"{max(hf)/P.CAP_I_RIPPLE_RATED:.2f}x the 2.70 A rating)")
        hf_ceil = [1800.0 * (P.CAP_I_RIPPLE_RATED / f) ** 2 for f in hf]
        print(f"    HF term ALONE reaches 2.70 A at P_out = "
              f"{min(hf_ceil):.0f}-{max(hf_ceil):.0f} W.")
        print("    Independent of mains voltage, mains current, rectifier")
        print("    topology and PFC.  A hard cap on column (a) everywhere.")

        # ------------------------------------------------------------ B
        print("\nB.  OPERATING POINT AT THE DECLARED 1800 W OUTPUT")
        hr("-")
        print(f"    {'supply':<10} {'topo':<8} {'case':<14} {'P_in':>6} "
              f"{'theta':>7} {'I_rms':>7} {'I_pk':>7} {'PF':>6} {'V_bus':>7} "
              f"{'Vpp':>6} {'/branch':>8}")
        for sup in SUPPLIES:
            for c in cases:
                op = op_at(sup, c, 1800.0)
                print(f"    {sup.key:<10} {sup.topology:<8} {c.name:<14} "
                      f"{op.p_in:6.0f} {op.theta_deg:6.1f}d "
                      f"{op.i_line_rms:7.2f} {op.i_line_pk:7.1f} {op.pf:6.3f} "
                      f"{op.v_bus_avg:7.1f} {op.v_bus_pp:6.1f} "
                      f"{op.i_line_rms/sup.i_branch:7.2f}x")

        # ------------------------------------------------------------ C
        built = {sup.key: build(sup, cases) for sup in SUPPLIES}

        print("\nC.  THE DECISION TABLE")
        hr("-")
        print("  (a) AS THE DESIGN STANDS -- every committed part at its rating")
        print(f"      {'supply':<10} {'ceiling':>14}   binding constraint")
        for sup in SUPPLIES:
            br, name = col(built[sup.key], cases, DROP_HEADLINE)
            print(f"      {sup.key:<10} {fmt_br(br):>14}   {name}")

        print("\n  (b) BUS-CAP + HF-BYPASS DEFECTS FIXED  [CONDITIONAL]")
        print("      capacitor-ripple constraint assumed retired; nothing else")
        print("      changed.  Depends on work not yet landed -- see the .md.")
        print(f"      {'supply':<10} {'ceiling':>14}   binding constraint")
        for sup in SUPPLIES:
            br, name = col(built[sup.key], cases, DROP_HEADLINE + ("C_BUS",))
            print(f"      {sup.key:<10} {fmt_br(br):>14}   {name}")

        print("\n  (b+) (b) AND the rectifier uprated past I_FRM = 30 A")
        print("       [CONDITIONAL, and an owner-unapproved BOM change].")
        print("       Shows what the PASSIVE front end can do with no PFC at")
        print("       all, i.e. which scenarios never need power-factor")
        print("       correction to hit their target.")
        print(f"      {'supply':<10} {'ceiling':>14}   binding constraint")
        for sup in SUPPLIES:
            br, name = col(built[sup.key], cases,
                           DROP_HEADLINE + ("C_BUS", "D I_FRM"))
            print(f"      {sup.key:<10} {fmt_br(br):>14}   {name}")

        print(f"\n  (c) (b) + PFC at PF = {PF_PFC} -- sinusoidal line current,")
        print("      so the rectifier peak collapses and I_FRM stops binding.")
        print(f"      {'supply':<10} {'ceiling':>14}   binding constraint")
        for sup in SUPPLIES:
            cands = {f"branch {sup.i_branch:.0f}A": sup.i_branch,
                     f"F1/L1 {P.I_FUSE_RATED:.0f}A": P.I_FUSE_RATED,
                     f"K1 IEC {P.I_K1_IEC:.0f}A": P.I_K1_IEC}
            vals, names = [], []
            for c in cases:
                sub = {k: pfc_ceiling(sup, c.eta, i) for k, i in cands.items()}
                k = min(sub, key=lambda kk: sub[kk])
                vals.append(sub[k])
                names.append(k)
            uniq = names[0] if len(set(names)) == 1 else " | ".join(names)
            print(f"      {sup.key:<10} {fmt_br(bracket(vals)):>14}   {uniq}")

        # ------------------------------------------------------------ D
        print("\nD.  FULL CEILING LADDER, central case")
        hr("-")
        for sup in SUPPLIES:
            lim = built[sup.key][cases[1].name]
            print(f"\n    {sup.key}  ({sup.topology}, {sup.plug}, "
                  f"{sup.f_hz:.0f} Hz, {sup.va:.0f} VA)")
            for k, v in sorted(lim.items(), key=lambda kv: kv[1]):
                print(f"        {k:<24} {fmt(v):>6} W")
        print()

    # ---------------------------------------------------------------- E
    hr()
    print("E.  SECONDARY / SEPARATELY-LABELLED LINES (never in a headline)")
    hr("-")
    print("  E.1  NEC-80% continuous-load ceilings, PFC assumed (PF 0.95).")
    print("       [standard] NEC 210.23(B)(1) (2023 ed.): the rating of any")
    print("       ONE cord-and-plug-connected utilization equipment not")
    print("       fastened in place shall not exceed 80% of the branch-")
    print("       circuit ampere rating.  Located this session; see the .md")
    print("       sec.5 for exactly what is and is not established about its")
    print("       applicability to this product.  NEC does not apply in the")
    print("       IEC rows: shown as n/a, and no IEC equivalent is invented.")
    for sup in SUPPLIES:
        if sup.i_cont is None:
            print(f"       {sup.key:<10} {'n/a (IEC market)':>18}")
            continue
        vals = [pfc_ceiling(sup, c.eta, sup.i_cont) for c in P.CASES]
        print(f"       {sup.key:<10} {fmt_br(bracket(vals)):>18}   "
              f"(I_cont = {sup.i_cont:.0f} A)")

    print(f"\n  E.2  PFC at an optimistic PF = {PF_PFC_BEST}, branch-limited")
    print("       only (F1/L1/K1 also re-rated to the branch -- an OWNER-")
    print("       UNAPPROVED BOM change, shown so the ideal is visible).")
    for sup in SUPPLIES:
        vals = [pfc_ceiling(sup, c.eta, sup.i_branch, PF_PFC_BEST)
                for c in P.CASES]
        print(f"       {sup.key:<10} {fmt_br(bracket(vals)):>18}")

    print("\n  E.3  Pure arithmetic ceiling: P_out = V*I*PF*eta at PF = 1.000")
    print("       (physically unreachable; the absolute upper bound).")
    for sup in SUPPLIES:
        vals = [sup.va * c.eta for c in P.CASES]
        print(f"       {sup.key:<10} {fmt_br(bracket(vals)):>18}   "
              f"({sup.va:.0f} VA branch)")

    # ---------------------------------------------------------------- F
    hr()
    print("F.  WHAT main.ato:494-495 SHOULD SAY, PER SCENARIO  (do NOT apply)")
    hr("-")
    print("  p_output_max is an OUTPUT power.  The correct value is whichever")
    print("  column the owner picks; the assertion band should BRACKET it")
    print("  rather than straddle an unreachable endpoint.  Tank variant")
    print("  'committed' throughout.")
    print(f"  {'supply':<10} {'(b) no PFC':>16} {'(c) PFC 0.95':>16} "
          f"{'NEC-80% + PFC':>16}")
    cases = cases_for("committed")
    for sup in SUPPLIES:
        built = build(sup, cases)
        br_b, _ = col(built, cases, DROP_HEADLINE + ("C_BUS",))
        br_c = bracket([min(pfc_ceiling(sup, c.eta, i)
                            for i in (sup.i_branch, P.I_FUSE_RATED,
                                      P.I_K1_IEC)) for c in cases])
        br_n = (bracket([pfc_ceiling(sup, c.eta, sup.i_cont) for c in cases])
                if sup.i_cont is not None else None)
        print(f"  {sup.key:<10} {fmt_br(br_b):>16} {fmt_br(br_c):>16} "
              f"{(fmt_br(br_n) if br_n else 'n/a'):>16}")

    # ---------------------------------------------------------------- G
    hr()
    print("G.  IEC 60335-1 cl.13.2/16.2 TOUCH-CURRENT LIMIT vs RATED INPUT")
    hr("-")
    print("  [repo, CITED-PRIMARY] docs/evidence/2026-07-30-c6-touch-current-")
    print("  budget-and-part2-routes.md:50 quotes IEC 60335-1 verbatim:")
    print('    "stationary class I heating appliances: 0,75 mA or 0,75 mA per')
    print('     kW rated power input ... whichever is higher" (max 5 mA)')
    print("  The limit MOVES WITH THE RATING -- and FLOORS at 0.75 mA, so")
    print("  ratings below 1 kW get NO relief while still losing budget:")
    print(f"  {'rated input (kW)':>18} {'touch-current limit':>22}")
    for kw in (0.5, 0.75, 0.9, 1.0, 1.2, 1.44, 1.5, 1.8, 2.0, 2.4, 3.0):
        lim = max(0.75, 0.75 * kw)
        note = ""
        if abs(kw - 1.8) < 1e-9:
            note = "  <- as declared today (domain_manifest.yaml: 1.35 mA)"
        elif kw <= 1.0:
            note = "  <- FLOOR binds; no relief below 1 kW"
        print(f"  {kw:>18.2f} {lim:>19.3f} mA{note}")

    # ---------------------------------------------------------------- H
    hr()
    print("H.  NUMERICAL CHECKS")
    hr("-")
    cases = cases_for("committed")
    print("  H.1 grid/step convergence (central case, 1800 W):")
    for sup in (SUPPLIES[0], SUPPLIES[3], SUPPLIES[5]):
        a = op_at(sup, cases[1], 1800.0, n_per_cycle=2000, n_cycles=30)
        b = op_at(sup, cases[1], 1800.0, n_per_cycle=8000, n_cycles=60)
        print(f"      {sup.key:<10} I_rms {a.i_line_rms:.4f} -> "
              f"{b.i_line_rms:.4f} A "
              f"({abs(b.i_line_rms-a.i_line_rms)/a.i_line_rms*100:.3f}%)  "
              f"theta {a.theta_deg:.2f} -> {b.theta_deg:.2f} deg  "
              f"LFeq {a.i_cap_unit_lf_eq:.3f} -> {b.i_cap_unit_lf_eq:.3f} A")
    print("\n  H.2 lumped-tail spectral method vs exact 100-harmonic sum:")
    for sup in (SUPPLIES[0], SUPPLIES[3], SUPPLIES[5]):
        a = op_at(sup, cases[1], 1800.0, exact_dft=False)
        b = op_at(sup, cases[1], 1800.0, exact_dft=True)
        d = (a.i_cap_unit_lf_eq - b.i_cap_unit_lf_eq) / b.i_cap_unit_lf_eq * 100
        print(f"      {sup.key:<10} lumped {a.i_cap_unit_lf_eq:.4f} A vs exact "
              f"{b.i_cap_unit_lf_eq:.4f} A  ({d:+.2f}%, "
              f"{'conservative' if d >= -0.05 else 'OPTIMISTIC -- investigate'})")
    print("\n  H.3 cross-check vs fe9cf6752 for 120V/15A at 1800 W")
    print("      (prior doc sec.1: I_rms 26.61 A, PF 0.697, theta 58.0 deg,")
    print("       V_bus 292.4 V, central case):")
    op = op_at(SUPPLIES[0], cases_for("superseded")[1], 1800.0)
    print(f"      here: I_rms {op.i_line_rms:.2f} A, PF {op.pf:.3f}, "
          f"theta {op.theta_deg:.1f} deg, V_bus {op.v_bus_avg:.1f} V")

    hr()
    print("Done.  No file written, no repo state read beyond the prior")
    print("committed evidence script, no board file opened.")


if __name__ == "__main__":
    main()
