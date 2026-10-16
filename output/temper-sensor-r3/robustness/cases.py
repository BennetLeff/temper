"""Case lists shared by the Python screen (hc_candidates.py) and the C co-sim (hc_cosim.py).

h-step set (HS, gated; robustness/DECISIONS.md R-HS):
  4 pans x h0 in {1000, the pan's design-spread geometric mean} x h1 in {600, 300}
  x t_step in {100 s (mid first ramp), 250 s (first hold), 365 s (second ramp),
  500 s (second hold)}: 64 cases, eta 0.88.
Reported alongside:
  HS_DEEP   h0 1000 -> 150 (below the adaptation floor) at 100 / 250 s;
  HS_BACK   1000 -> 300 at 250 s, back to 1000 at 450 s (re-seated);
  HS_GRAD   warp as the pan heats: h0 -> 300 log-linear over 100-160 s, and
            over 250-370 s (a gradual change is not an event and is not caught).
Plus the screen.py-derived design / nominal / food / loss cases (same seeds).
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "temper-sensor-r2"))
sys.path.insert(0, str(HERE.parent))
import estimator_study as es  # noqa: E402
import screen  # noqa: E402

PANS = ("carbon_steel_28", "triply_clad_24", "cast_iron_26", "disc_pot_water_1l5")
T_STEPS = (100.0, 250.0, 365.0, 500.0)
LOSS_T = FOOD_T = 250.0


def spread():
    screen.apply(screen.CANDS["C1"])
    return screen.h_spread(screen.CANDS["C1"])


def h_mid(pan):
    lo, hi = spread()[pan]
    return round((lo * hi) ** 0.5, 0)


def hs_cases():
    out = []
    i = 0
    for pan in PANS:
        for h0 in (1000.0, h_mid(pan)):
            for h1 in (600.0, 300.0):
                for ts in T_STEPS:
                    out.append(dict(kind="hs", pan=pan, h=h0, eta=0.88, seed=900 + i, h_spec=("step", ts, h1),
                                    ev_at=(ts,), label=f"{h0:.0f}->{h1:.0f}@{ts:.0f}"))
                    i += 1
    return out


def report_cases():
    out = []
    i = 0
    for pan in PANS:
        for ts in (100.0, 250.0):
            out.append(dict(kind="hs_deep", pan=pan, h=1000.0, eta=0.88, seed=1000 + i,
                            h_spec=("step", ts, 150.0), ev_at=(ts,), label=f"1000->150@{ts:.0f}"))
            i += 1
        out.append(dict(kind="hs_back", pan=pan, h=1000.0, eta=0.88, seed=1000 + i,
                        h_spec=(("step", 250.0, 300.0), ("step", 450.0, 1000.0)), ev_at=(250.0, 450.0),
                        label="1000->300@250->1000@450"))
        i += 1
        h0 = h_mid(pan)
        for (t0, t1) in ((100.0, 160.0), (250.0, 370.0)):
            out.append(dict(kind="hs_grad", pan=pan, h=h0, eta=0.88, seed=1000 + i,
                            h_spec=("ramp", t0, t1, 300.0), ev_at=(t0,), settle=t1 - t0 + 20.0,
                            label=f"{h0:.0f}->300 ramp {t0:.0f}-{t1:.0f}"))
            i += 1
    return out


def base_cases():
    """screen.py's C1 design, nominal, food and loss runs (same seeds as screen.py / cosim.py)."""
    sp = spread()
    out = []
    i = 0
    for pan, (lo, hi) in sp.items():
        for h in (lo, hi):
            for eta in es.ETA_SWEEP:
                out.append(dict(kind="design", pan=pan, h=h, eta=eta, seed=100 + i))
                i += 1
    i += 12                          # screen.py's stress cases take seeds 300 + 16 .. 27
    for pan, (lo, hi) in sp.items():
        h = (lo * hi) ** 0.5
        out.append(dict(kind="loss", pan=pan, h=h, eta=0.82, seed=500 + i, loss_at=LOSS_T))
        out.append(dict(kind="nominal", pan=pan, h=h, eta=0.82, seed=500 + i))
        if pan != "disc_pot_water_1l5":
            out.append(dict(kind="food", pan=pan, h=h, eta=0.82, seed=500 + i, food_at=FOOD_T))
        i += 1
    return out


def stress_cases():
    """screen.py's 12 C1 stress cases (h_c outside the design spread, constant), same seeds."""
    out = []
    i = 16
    for pan in es.PANS:
        for h in screen.STRESS_H:
            out.append(dict(kind="stress", pan=pan, h=h, eta=0.82, seed=300 + i))
            i += 1
    return out


def b3_limit(pan):
    return 1.5 if es.PANS[pan]["sp"][1] <= 100 else 3.0


# ---- Problem B: contaminated contact (contaminants.py) ---------------------------------
# Each case: thermal pan, dry h, and a truth spec {"kind": "water"|"sticky"|"contact", ...}.
# Pan classes for the contact values: carbon_steel_28 <- carbon_steel, cast_iron_26 <-
# cast_iron_as_cast (worst), triply_clad_24 <- clad_polished_ss, water pot <- disc_base_brushed.
CLASS_OF = {"carbon_steel_28": "carbon_steel", "cast_iron_26": "cast_iron_as_cast",
            "triply_clad_24": "clad_polished_ss", "disc_pot_water_1l5": "disc_base_brushed"}
DRY_PANS = ("carbon_steel_28", "cast_iron_26", "triply_clad_24")


def contaminant_cases():
    import contaminants as ct
    oil, _ = ct.oil_table()
    wat = ct.water_table()
    crud = ct.crud_table()
    out = []
    i = 0

    def add(group, pan, h, spec, label, **kw):
        nonlocal i
        out.append(dict(kind="contam", group=group, pan=pan, h=float(h), eta=0.88, seed=1200 + i, truth=spec,
                        label=label, **kw))
        i += 1

    for pan in cs_pans_all():
        cls = CLASS_OF[pan]
        dry, o = oil[cls]["dry"], oil[cls]
        # oil: wet film from the start (k range), drip mid-cook (step up), varnish (series film)
        add("oil", pan, o["oil_wet_k0.17"], None, f"oil-wet from start h {o['oil_wet_k0.17']}")
        add("oil", pan, o["oil_wet_k0.15"], None, f"oil-wet from start h {o['oil_wet_k0.15']}")
        for ts in (100.0, 250.0):
            add("oil", pan, dry, None, f"oil drip @{ts:.0f}: {dry}->{o['oil_wet_k0.17']}",
                h_spec=("step", ts, float(o["oil_wet_k0.17"])), ev_at=(ts,))
        for tv in (30, 60, 100):
            add("oil", pan, o[f"varnish_{tv}um_k0.15"], None, f"varnish {tv} um k0.15 h {o[f'varnish_{tv}um_k0.15']}")
    for pan in DRY_PANS:
        cls = CLASS_OF[pan]
        w = wat[cls]
        for m in (0.05e-3, 0.15e-3, 0.35e-3):
            for t_in, T_in in ((0.0, 20.0), (100.0, 20.0), (250.0, 20.0)):
                for bs in (1.0, 0.3):
                    add("water", pan, w["dry"], dict(kind="water", m_w0=m, t_in=t_in, T_in=T_in, h_liq=w["liquid_gap"],
                                                     h_vap=w["vapour_gap"], boil_scale=bs),
                        f"water {m * 1e6:.0f} mg @{t_in:.0f} s boil x{bs}", ev_at=(t_in,) if t_in else None,
                        settle=60.0)
        c = crud[cls]
        add("crud", pan, c["partial_Ff1.0N_tilt5mrad"], None, f"partial stick Ff 1.0 N, tilt 5 mrad h {c['partial_Ff1.0N_tilt5mrad']}")
        for dmax in (0.1e-3, 0.2e-3, 0.3e-3):
            add("crud", pan, c["dry"], dict(kind="sticky", cls=cls, delta_max=dmax, t_stick=0.0),
                f"stuck from start, bow {dmax * 1e3:.1f} mm")
        for gap in (0.1e-3, 0.2e-3):
            add("crud", pan, c["dry"], dict(kind="sticky", cls=cls, delta_max=0.1e-3, t_stick=0.0,
                                            gap_step=(250.0, gap)),
                f"stuck, bow 0.1 mm, nudged +{gap * 1e3:.1f} mm @250", ev_at=(250.0,))
    return out


def cs_pans_all():
    return PANS


def make_truth(spec):
    """Truth factory for a contaminant spec (picklable: built inside the worker)."""
    import contaminants as ct
    if spec is None:
        return None
    kw = {k: v for k, v in spec.items() if k != "kind"}
    if spec["kind"] == "water":
        return lambda pan, h0, eta, seed, food_at: ct.WaterTruth(pan, h0, eta, seed, food_at=food_at, **kw)
    if spec["kind"] == "sticky":
        return lambda pan, h0, eta, seed, food_at: ct.StickyTruth(pan, h0, eta, seed, food_at=food_at, **kw)
    raise ValueError(spec)
