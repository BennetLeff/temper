#!/usr/bin/env python3 -I
"""Parametrised touch-current (DESIGN-row) model.

The physics, constants and scenario rule are imported from repo_copies/leakage_budget.py, a byte-identical copy of the
committed zapote/power-stage-120v/validation-results/07-conducted-emi/leakage/leakage_budget.py (sha256 in MANIFEST.json):
  open-PE touch current per polarity = sum over the hot line of  w*C*V  (every Y at +20 %, coil 31 pF at +20 %)
                                       + each mains-connected supply's datasheet maximum, scaled x V/V_test x 60/50.
Only the inputs are parametrised here (board Y, module Y, supply list, R38/PS2 path variants); nothing in the rule changes.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("leakage_budget_copy", HERE / "repo_copies/leakage_budget.py")
lb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lb)

V, TOL, FREQ_FACTOR = lb.V_LINE, lb.TOL, lb.SUPPLY_FREQ_FACTOR
LIMITS = {"portable_0.5": 0.5, "stationary_0.75": 0.75}
PASS_FRACTION = lb.PASS_FRACTION  # 0.5: the fixed project rule (total <= 50 % of the limit)

# Supply datasheet maxima.  Each row: (max leakage mA, test voltage V, source).  See SOURCES in parts_db.py.
SUPPLIES = {
    "IRM-20-15": (0.25, 277.0, "MEAN WELL IRM-20-SPEC 2025-11-21, p.2 spec table, LEAKAGE CURRENT '< 0.25mA/277Vac'"),
    "IRM-20-24": (0.25, 277.0, "MEAN WELL IRM-20-SPEC 2025-11-21, p.2 spec table, LEAKAGE CURRENT '< 0.25mA/277Vac'"),
    "IRM-60-15ST": (0.25, 277.0, "MEAN WELL IRM-60-SPEC 2025-11-21, p.2 spec table, LEAKAGE CURRENT '< 0.25mA/277Vac'"),
    "MPM-20-15": (0.080, 264.0, "MEAN WELL MPM-20-SPEC 2024-10-30, p.2 spec table, LEAKAGE CURRENT (max.) 'Touch current <80uA/264VAC', "
                                "Note 7 'measured from primary input to DC output'"),
    "MPM-20-24": (0.080, 264.0, "MEAN WELL MPM-20-SPEC 2024-10-30, p.2 (as MPM-20-15)"),
    "MPM-65-15ST": (0.100, 264.0, "MEAN WELL MPM-65-SPEC 2024-10-30, p.2 spec table, LEAKAGE CURRENT (max.) 'Touch current <100uA/264VAC', "
                                  "Note 6 'measured from primary input to DC output'"),
}


def i_y(c_nom_f):
    return lb.i_ma(c_nom_f * (1 + TOL))


def supply_ma(mpn, v=V):
    mx, vt, _ = SUPPLIES[mpn]
    return mx * (v / vt) * FREQ_FACTOR


COIL_MA = lb.i_ma(31e-12 * (1 + TOL))
MA_PER_NF = lb.i_ma(1e-9 * (1 + TOL))


def touch(board_y_nF, module_y_nF, supplies, counted=None):
    """DESIGN-row open-PE touch current (mA) per polarity.  `supplies`: list of MPNs fitted; `counted`: the subset whose
    leakage is charged to the PE path (default: all, which is the committed DESIGN rule)."""
    counted = supplies if counted is None else counted
    y = (board_y_nF + module_y_nF) * MA_PER_NF
    s = sum(supply_ma(x) for x in counted)
    return y + COIL_MA + s


def y_ceiling_nF(limit_mA, supplies_counted, fraction=PASS_FRACTION):
    """Largest total nominal Y per line (board + module) that keeps touch <= fraction x limit."""
    rem = fraction * limit_mA - COIL_MA - sum(supply_ma(x) for x in supplies_counted)
    return rem / MA_PER_NF  # may be negative = impossible


def verdicts(t_mA):
    out = {}
    for k, lim in LIMITS.items():
        out[f"{k}_50pct_budget_{PASS_FRACTION*lim:.3f}"] = t_mA <= PASS_FRACTION * lim + 1e-12
        out[f"{k}_100pct"] = t_mA <= lim + 1e-12
    return out
