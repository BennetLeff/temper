#!/usr/bin/env python3
"""Build the A70QS50-14F manufacturer application-review packet.

Reproducible: computes the representative discharge cases from the same series
R-L-C model the campaign envelope uses, oracle-checks them, and writes the
packet with those numbers embedded.

The representative cases are illustrative points ON the campaign's envelope, not
new measurements. The retained envelope and its oracles live in
../attempt-001/raw/compute_result.json and ../AR-COORD/attempt-001/raw/.

Run:  python3 build_packet.py
"""

from __future__ import annotations

import json
import math
import pathlib

from scipy import optimize

C_BANK_F = 2240.47e-6
V_BUS_V = 400.0
E_BANK_J = 0.5 * C_BANK_F * V_BUS_V**2

HERE = pathlib.Path(__file__).resolve().parent
OUT_MD = HERE / "A70QS50-14F-application-review.md"
OUT_JSON = HERE / "representative-cases.json"

# The loop bounds are read from the AR-BOUNDS attempt, not copied: one source.
BOUNDS = json.loads((HERE / "../../AR-BOUNDS/attempt-001/result.json").read_text())

# (label, R ohm, L H)
CASES = [
    ("Envelope peak corner", 5e-3, 20e-9),
    ("Most underdamped cell (= the 4.00 ms exclusion)", 5e-3, 20e-6),
    ("Second exclusion: tau = 2.52 ms", 5e-3, 12.62e-6),
    ("Mid-damped, low R", 5.0e-2, 20e-6),
    ("Near-critical (zeta ~ 1)", 2.0e-1, 20e-6),
    ("Screen edge: R = 0.64013 ohm", 0.6401342857142858, 20e-6),
    ("Most damped envelope corner", 5.0, 20e-6),
]


def response(r: float, l: float, t: float) -> float:
    """Series R-L-C discharge current, C precharged to V0, i(0)=0.

    Overdamped uses the two-real-exponential form, which cannot overflow:
    both exponents are <= 0 for t >= 0, whereas sinh(.) does overflow at the
    high zeta values this envelope reaches (zeta up to ~800).
    """
    w0 = 1.0 / math.sqrt(l * C_BANK_F)
    zeta = (r / 2.0) * math.sqrt(C_BANK_F / l)
    if zeta < 1.0:
        wd = w0 * math.sqrt(1.0 - zeta * zeta)
        return (V_BUS_V / (wd * l)) * math.exp(-zeta * w0 * t) * math.sin(wd * t)
    if zeta == 1.0:
        return (V_BUS_V / l) * t * math.exp(-w0 * t)
    root = w0 * math.sqrt(zeta * zeta - 1.0)
    s1 = -zeta * w0 + root          # slower pole (closer to zero)
    s2 = -zeta * w0 - root          # faster pole
    return (V_BUS_V / (l * (s1 - s2))) * (math.exp(s1 * t) - math.exp(s2 * t))


def horizon(r: float, l: float) -> float:
    """Integration horizon: long enough for the response to die out."""
    w0 = 1.0 / math.sqrt(l * C_BANK_F)
    zeta = (r / 2.0) * math.sqrt(C_BANK_F / l)
    if zeta < 1.0:
        wd = w0 * math.sqrt(1.0 - zeta * zeta)
        return max(10.0 / (zeta * w0), 5.0 * 2.0 * math.pi / wd)
    if zeta == 1.0:
        return 10.0 / w0
    root = w0 * math.sqrt(zeta * zeta - 1.0)
    s1 = -zeta * w0 + root
    return min(10.0 / abs(s1), 0.5)


def first_lobe_end(r: float, l: float) -> float:
    """An upper bound t where the current is still rising toward its first peak."""
    w0 = 1.0 / math.sqrt(l * C_BANK_F)
    zeta = (r / 2.0) * math.sqrt(C_BANK_F / l)
    if zeta < 1.0:
        return math.pi / (w0 * math.sqrt(1.0 - zeta * zeta))
    if zeta == 1.0:
        return 5.0 / w0
    root = w0 * math.sqrt(zeta * zeta - 1.0)
    s1 = -zeta * w0 + root
    s2 = -zeta * w0 - root
    return 5.0 * math.log(s1 / s2) / (s2 - s1)


def peak_current(r: float, l: float) -> tuple[float, float]:
    """Return (peak_a, t_peak_s) by bounded golden-section search.

    Not a uniform grid: at high R, L/R is ~20 ns while the slow-pole tail runs
    to ~100 ms, and no single uniform step resolves both (the under-resolved
    peak is exactly what the V0/R oracle catches).
    """
    res = optimize.minimize_scalar(
        lambda t: -response(r, l, t),
        bounds=(0.0, first_lobe_end(r, l)),
        method="bounded",
        options={"xatol": 1e-15},
    )
    return -res.fun, res.x


def action_quad(r: float, l: float) -> float:
    """Numerically integrate the action i^2 dt. Used ONLY as an oracle check.

    The reported action is E/R by energy balance (exact); this routine exists
    to show that an independent quadrature reproduces it. Composite Simpson on
    two segments (fast transient, then slow/oscillatory tail) rather than one
    adaptive call, because either scale alone defeats a single grid.
    """
    t_peak, _ = peak_current(r, l)
    t_end = horizon(r, l)
    t1 = min(t_end, 20.0 * t_peak)
    total = 0.0
    for a, b, n in ((0.0, t1, 200_000), (t1, t_end, 600_000)):
        if b <= a:
            continue
        h = (b - a) / n
        s = response(r, l, a) ** 2 + response(r, l, b) ** 2
        for k in range(1, n):
            s += (4.0 if k % 2 else 2.0) * response(r, l, a + k * h) ** 2
        total += s * h / 3.0
    return total


rows = []
for label, r, l in CASES:
    zeta = (r / 2.0) * math.sqrt(C_BANK_F / l)
    tau = l / r
    peak, t_peak = peak_current(r, l)
    action = E_BANK_J / r  # exact: all stored energy is dissipated in R
    rows.append(
        {
            "label": label,
            "r_ohm": r,
            "l_h": l,
            "tau_l_over_r_s": tau,
            "zeta": zeta,
            "peak_a": peak,
            "t_peak_s": t_peak,
            "action_a2s": action,
            "action_basis": "E/R by energy balance (exact)",
            "action_screen_met": action >= 280.0 and r <= 0.6401342857142858,
            "tau_condition_met": tau <= 2.5e-3,
        }
    )

# Oracle checks. Each must be evaluated where its limit actually holds:
# V0/R needs R >> Z0 (large R, small L); V0/Z0 needs R << Z0 (near-lossless,
# small R, large L). Checking the lossless bound at zeta ~ 0.8 would be a
# mis-set-up instrument, not a failing model.
checks = []
for label, r, l in [("5 ohm / 20 nH", 5.0, 20e-9), ("1 ohm / 20 nH", 1.0, 20e-9)]:
    peak, _ = peak_current(r, l)
    checks.append(
        {
            "check": f"peak({label}, zeta={((r / 2) * math.sqrt(C_BANK_F / l)):.0f}) -> V0/R",
            "computed": peak,
            "reference": V_BUS_V / r,
            "rel_err": abs(peak - V_BUS_V / r) / (V_BUS_V / r),
        }
    )
peak_lossless, _ = peak_current(1e-4, 20e-6)
z0 = math.sqrt(20e-6 / C_BANK_F)
checks.append(
    {
        "check": "peak(0.1 mOhm, 20 uH, zeta~5e-4) -> V0/Z0 (lossless limit)",
        "computed": peak_lossless,
        "reference": V_BUS_V / z0,
        "rel_err": abs(peak_lossless - V_BUS_V / z0) / (V_BUS_V / z0),
    }
)
for r in (0.05, 0.6401342857142858, 5.0):
    act = action_quad(r, 20e-6)
    checks.append(
        {
            "check": f"action quadrature (R={r:g} ohm, 20 uH) -> E/R",
            "computed": act,
            "reference": E_BANK_J / r,
            "rel_err": abs(act - E_BANK_J / r) / (E_BANK_J / r),
        }
    )

worst = max(c["rel_err"] for c in checks)
assert worst < 0.02, f"oracle disagreement {worst}"

OUT_JSON.write_text(
    json.dumps(
        {
            "bank": {"c_bank_f": C_BANK_F, "v_bus_v": V_BUS_V, "energy_j": E_BANK_J},
            "cases": rows,
            "oracle_checks": checks,
            "max_oracle_rel_err": worst,
        },
        indent=2,
    )
    + "\n"
)

for c in checks:
    print(f"  oracle {c['check']}: rel_err {c['rel_err']:.3e}")
print(f"  worst oracle rel_err = {worst:.3e}")

lines = []
W = lines.append

W("# Manufacturer application review — Mersen A70QS50-14F")
W("")
W("**Prepared:** 2026-09-18  ")
W("**Subject:** confirmation of the capacitor-discharge application conditions")
W("for A70QS50-14F against a described 400 Vdc bus discharge.")
W("")
W("**Status of this document.** It is a *request for confirmation*, and a record")
W("of the conditional screening already done. Nothing here is a qualified")
W("operating point, a demonstrated coordination, or a hardware result. The")
W("quantities we are least sure of are listed as such, and the questions we need")
W("answered are specific.")
W("")
W("---")
W("")
W("## 1. Application")
W("")
W("A single-phase boost power-factor-correction front end for an induction")
W("cooker: mains rectifier, boost inductor and switch, 400 Vdc bus with an")
W("electrolytic bank, feeding a quasi-resonant inverter. The fuse under")
W("consideration is the **A70QS50-14F** (50 A, 14 x 51 mm French cylindrical),")
W("evaluated as a bus-side candidate.")
W("")
W(f"**Bus bank energy:** {C_BANK_F * 1e6:.2f} uF at {V_BUS_V:.0f} Vdc =")
W(f"**{E_BANK_J:.2f} J** stored, modelled as a single lumped capacitor.")
W("")
W("## 2. The condition we are screening against")
W("")
W("We read the A70QS page (catalogue p.20 / HS 20) as stating:")
W("")
W("> ... these fuses have an **890 VDC rating for capacitor discharge")
W("> applications up to 2.5 ms time constant**.")
W("")
W("We read \"time constant\" as **L/R**, on the basis that the catalogue's DC")
W("tables state `*Time Constant: L/R <= 1ms`, and the same A70QS page uses")
W("`L/R <= 10 ms` and `10 ms time constant` interchangeably for its general DC")
W("rating. **We are not certain the capacitor-discharge sentence uses the same")
W("definition** — the explicit `L/R` statements concern the general DC ratings")
W("and other product lines. Question 1 asks you to confirm it.")
W("")
W("## 3. Fault scenario being analysed")
W("")
W("**This inquiry evaluates U10 and U9 both failed short.** The loop also")
W("exists with U10 shorted and a healthy U9 conducting; that separate case")
W("does not establish shutdown without detection, latency and survival evidence.")
W("")
W("- **U10 (the boost diode, C3D20065D) fails short.** This is what connects the")
W("  400 Vdc bus to the switch node `a1`. Without it, a healthy U10 is")
W("  reverse-biased and **blocks the discharge entirely** — a bare boost-switch")
W("  short does *not* discharge the bank. That was established earlier in this")
W("  work and is the reason U10 is named as a failed device rather than a")
W("  conducting one.")
W("- **U9 (the boost switch, STW65N65DM2AG) fails short.** This completes the")
W("  loop from `a1` to the bus return. It is specified as *failed* short, not")
W("  merely gated on. A healthy U9 might interrupt after detection, but no")
W("  detection/latency or turn-off-survival credit is taken in this inquiry.")
W("- **F2, a proposed series high-speed DC fuse in the bus path**, sits in this")
W("  loop. With U9 failed short it is the **only** element that can interrupt,")
W("  which is why its capacitor-discharge capability is the question.")
W("")
W("The proposed stored-energy loop is `bank+ -> F2 -> U10 (short) -> a1 ->")
W("U9 (short) -> PFC_BUS_MINUS -> bank-`. U12 (shunt) and F1 are outside")
W("this loop. The bank and U9 source share PFC_BUS_MINUS; U12 bridges that")
W("net to the rectifier-side minus net. F2 is proposed, not present in CAD.")
W("")
W("The loop's resistance and inductance are **not known**. They are swept rather")
W("than asserted:")
W("")
W("| Quantity | Envelope swept |")
W("| --- | --- |")
W("| Loop resistance R | 5 mOhm to 5 ohm |")
W("| Loop inductance L | 20 nH to 20 uH |")
W("")
W("These are sensitivity cases, not proven application limits. Peak current")
W("depends on both R and L; the largest L/R occurs at high L and low R.")
W("Section 4 gives what we can currently estimate for this board, together with")
W("what those estimates are not.")
W("")
_rd = BOUNDS["resistance_decomposition"]
_ld = BOUNDS["inductance_decomposition"]
_sl = BOUNDS["screen_location"]
W("## 4. R and L for this board: estimates, with their assumptions")
W("")
W("These are **estimates under stated assumptions**, not proven bounds. We are")
W("giving them so the inquiry carries real numbers; we are not asking you to")
W("treat any of them as established. Components with no published figure are")
W("left null rather than filled with a plausible default.")
W("")
W("| Term | Estimate | Basis and what it is *not* |")
W("| --- | ---: | --- |")
W(f"| Copper R, 20 C | {_rd['copper']['value_ohm_lower'] * 1e3:.2f} mOhm | geometry-derived from the least-resistance *extracted path* per capacitor |")
W(f"| Copper R, 100 C | {_rd['copper']['value_ohm_upper'] * 1e3:.2f} mOhm | same method, elevated temperature |")
W(f"| Fuse R | {_rd['fuse_resistance']['value_ohm'] * 1e3:.2f} mOhm | derived from 11.6 W at 50 A; a *hot* figure, so onset R is lower |")
W(f"| Bank ESR, per bank | {_rd['bank_esr']['value_ohm'] * 1e3:.2f} mOhm | from tan-delta max at **120 Hz** and nominal capacitance |")
W("| U9 failed-short residual | **null** | not published |")
W("| U10 failed-short residual | **null** | not published |")
W("")
W("Three caveats that matter more than the numbers:")
W("")
W("1. **The copper figure is not a lower bound — it is a path estimate, and it")
W("   tends to over-state.** It comes from tracing a single least-resistance")
W("   path per capacitor, and other conductors (including the return-side B.Cu")
W("   zone) were excluded from the sum. **Parallel paths can only reduce the")
W("   effective resistance**, so the extracted-path figure sits above the true")
W("   network value and cannot bound it from below.")
W("2. **The ESR figure is a 120 Hz estimate, not a broadband bound.** It uses")
W("   nominal capacitance, whereas the parts carry a +/-20% tolerance that alone")
W("   moves the derived ESR by roughly a quarter, and it extends a 120 Hz")
W("   loss-angle specification to the discharge waveform without evidence that")
W("   the specification holds there.")
W("3. **The listed resistances belong to different device states and must not be")
W("   added into one subtotal.** In particular, U9's healthy on-resistance")
W("   applies when U9 is *not* shorted; in the fault being analysed U9 is short")
W("   and that term does not apply. There is also no published short residual to")
W("   put in its place.")
W("")
W(f"**Inductance: an estimate of roughly {_ld['copper']['value_h_lower'] * 1e9:.0f} nH to")
W(f"{_ld['copper']['value_h_upper'] * 1e6:.1f} uH**, the span coming from the")
W("**return-path assumption** (return current directly beneath the forward trace")
W("versus horizontally offset by the measured 34.5 mm worst case). Bank, fuse")
W("and semiconductor-package internal inductances are not published and we have")
W("**not** bounded them; they add an unknown amount above these figures.")
W("")
W("**Where this leaves the location: INDETERMINATE — and deliberately so.**")
W("Neither the copper resistance nor the inductance is bounded on the evidence")
W("we have, and the two failed-short residuals that dominate the resistance are")
W("unpublished. We therefore cannot say whether the real discharge lands inside")
W(f"the screened region `{{400*L <= R <= 0.64013 ohm}}` or outside it, and we are")
W("not asserting either. This is the gap the questions in Section 7 are aimed")
W("at.")
W("")
W("## 5. Representative discharge cases")
W("")
W("Computed from the series R-L-C model (lumped C, constant R), and reproduced")
W("in `representative-cases.json`. `tau` is `L/R`, the quantity we believe your")
W("2.5 ms condition refers to; `zeta` is the damping factor, given because it")
W("governs how oscillatory the real waveform is.")
W("")
W("| Case | R | L | tau = L/R | zeta | Peak | Action |")
W("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")


def fmt_r(r: float) -> str:
    return f"{r * 1e3:.3g} mOhm" if r < 0.1 else f"{r:.3g} ohm"


def fmt_l(l: float) -> str:
    return f"{l * 1e9:.3g} nH" if l < 1e-6 else f"{l * 1e6:.3g} uH"


def fmt_tau(t: float) -> str:
    return f"{t * 1e6:.3g} us" if t < 1e-3 else f"{t * 1e3:.3g} ms"


for row in rows:
    W(
        f"| {row['label']} | {fmt_r(row['r_ohm'])} | {fmt_l(row['l_h'])} "
        f"| {fmt_tau(row['tau_l_over_r_s'])} | {row['zeta']:.3g} "
        f"| {row['peak_a'] / 1e3:.2f} kA | {row['action_a2s']:.0f} A2s |"
    )
W("")
W("**Action basis.** The Action column is `E/R` exactly, by energy balance:")
W("all the stored energy is dissipated in the loop resistance, so")
W(f"`integral(i^2 dt) = {E_BANK_J:.2f}/R`. It is not a numerical approximation,")
W("and it is the quantity we compare against the **maximum** pre-arcing figure")
W("of 280 A2s. A separate quadrature reproduces it to better than 1e-6 relative.")
W("")
W("**Waveform character.** Two regimes occur in the swept range and we need")
W("guidance on the applicable one:")
W("")
W("- **Underdamped** (`zeta << 1`, e.g. 5 mOhm / 20 uH, `zeta = 0.0265`): the")
W("  current rings, and `L/R` understates how long energy stays in the loop.")
W("  The oscillation-envelope decay is `2L/R` (8.0 ms at that corner), not `L/R`")
W("  (4.0 ms).")
W("- **Overdamped** (`zeta > 1`, e.g. 0.64 ohm / 20 uH): a unipolar pulse.")
W("")
W("## 6. What we have screened, and what it does not mean")
W("")
W("Intersecting the envelope with the conditions we could read:")
W("")
W("- **Pre-arcing action screen** (adiabatic, L-independent): `E/R` versus the")
W("  catalogue's **maximum** pre-arcing I2t of 280 A2s. Met for")
W("  `R <= 0.640 ohm`. This is an **available-action screen, not a melting")
W("  result** — it does not establish melting across arbitrary pulse durations,")
W("  temperatures and fuse tolerances.")
W("- **Time-constant condition** `L/R <= 2.5 ms`: 2 of those cells fail, at")
W("  (5 mOhm, 12.62 uH) and (5 mOhm, 20 uH).")
W("- **Peak current**: up to 55.2 kA, screened only against the **general**")
W("  100 kA DC interrupting rating — a different condition from capacitor")
W("  discharge.")
W("")
W("**Result: 142 of 400 swept cells pass these screens.** They are *not*")
W("qualified operating points. The capacitor-discharge current limit is")
W("**unknown**, and the general DC figure was used in its place; that gap is")
W("exactly what Question 2 addresses.")
W("")
W("## 7. Questions")
W("")
W("**Q1 — Time-constant definition.** Does the 2.5 ms time constant in the")
W("capacitor-discharge sentence mean `L/R`? If the applicable definition differs")
W("for oscillatory discharges, what is it, and how should an underdamped case")
W("(`zeta = 0.027`) be evaluated against the rating?")
W("")
W("**Q2 — Applicable current limit.** The 890 Vdc capacitor-discharge rating")
W("carries no separately published peak-current limit; we could only use the")
W("general 100 kA DC interrupting rating (`L/R = 11.6 ms`). What peak current")
W("limit applies to capacitor discharge at 890 Vdc, and does the 100 kA general")
W("figure remain valid for a discharge with a much shorter or oscillatory")
W("waveform?")
W("")
W("**Q3 — Minimum breaking current.** The A70QS line publishes no MBC column in")
W("this catalogue (the D70QS and D100QS lines do). What is the minimum breaking")
W("current for A70QS50-14F at the 890 Vdc capacitor-discharge condition? This")
W("decides whether a high-impedance fault is cleared or merely held.")
W("")
W("**Q4 — Capacitor-discharge let-through.** Is there a DC or")
W("capacitor-discharge **total clearing I2t** (let-through) characteristic for")
W("A70QS50-14F, valid at the 890 Vdc condition? The catalogue's only clearing")
W("figure is 1500 A2s at 700 V**AC**, which we cannot apply to this DC case.")
W("Without this, we cannot compare against a bank/copper withstand I2t, and")
W("clearing stays undemonstrated.")
W("")
W("Also, if a capacitor-discharge-specific datasheet or application note exists")
W("for the A70QS range, that is the single most useful document you could")
W("provide.")
W("")
W("## 8. What we would do with each answer")
W("")
W("| Answer | Consequence |")
W("| --- | --- |")
W("| Q1: `L/R` confirmed | Re-map as a plain `L/R` test; the 2 excluded cells stand and the screen becomes well-defined. |")
W("| Q1: a different definition | Re-derive the exclusion set; an underdamped case could be outside the rating at a much higher `R`. |")
W("| Q2: a lower cap-discharge peak limit | Re-cut the region; at 55 kA peak this could exclude the low-impedance cells entirely. |")
W("| Q3: an MBC above our low-current faults | The fuse would not clear high-impedance faults; the protection claim would need restructuring. |")
W("| Q4: a let-through I2t | Compare against a sourced bank/copper withstand I2t — one input to coordination, alongside applicable fault, current, duty and withstand evidence. |")
W("")
W("## 9. What we are not claiming")
W("")
W("- Not a qualified operating point. The loop's R and L are unknown; the")
W("  envelope is a sweep, and only one unknown cell in it is real.")
W("- Not a demonstrated coordination. No let-through figure and no sourced")
W("  bank/copper withstand exist yet (Q4).")
W("- Not a melting result. The action screen is a screen.")
W("- Not a hardware result. No bench or powered testing has been performed.")
W("- **Not an established bound.** The R and L figures in Section 4 are")
W("  estimates under stated assumptions; the question we are asking you does")
W("  not depend on their being proven limits.")
W("- Not a CAD or BOM change. A70QS50-14F is a candidate, not a design change.")
W("")
W("## 10. Provenance")
W("")
W("- Catalogue quoted: Mersen *High Speed Fuses* (2024-12-16), PDF sha256")
W("  `e0e5b788fcc883650ff771c4fa006986fec4238293856ab200b56e2cf44e9789`,")
W("  A70QS pages PDF p.20 (HS 20) and p.21 (HS 21).")
W("- Bank/energy constants: 2240.47 uF, 400 V, 179.2376 J.")
W("- Envelope: 25 R x 16 L = 400 cells, R in [5 mOhm, 5 ohm], L in [20 nH,")
W("  20 uH]; retained at")
W("  `../attempt-001/raw/compute_result.json` and")
W("  `../AR-COORD/attempt-001/raw/compute_result.json`.")
W("- Representative cases in this packet: `representative-cases.json`, computed")
W("  by `build_packet.py` with the same model; oracle checks on peak and action")
W(f"  agree to a worst relative error of {worst:.2e}.")
W("- Loop R and L figures: AR-BOUNDS attempt-001, derived from")
W("  `zapote/power-entry/shunt-repair/candidate/section.kicad_pcb`")
W("  (sha256 `34e6fba9...`), which is the board the AR-FAULT fault netlist was")
W("  taken from. That is deliberately *not* `pcb/temper.kicad_pcb`, which")
W("  contains none of the loop nets.")
W("")
W("**Correction notice.** An earlier revision of this packet presented the same")
W("numbers as established bounds ('R >= 10.29 mOhm', a 'sourced sub-total', and a")
W("0.4466 ohm crossing threshold). Those bound claims are **withdrawn**: the")
W("copper figure is a single-path estimate excluding parallel conductors, the ESR")
W("figure is a 120 Hz nominal-capacitance estimate, and the components belong to")
W("different device states. The numbers are unchanged; their status is not.")
W("")

OUT_MD.write_text("\n".join(lines) + "\n")
print(f"  wrote {OUT_MD.relative_to(pathlib.Path.cwd())}")
print(f"  wrote {OUT_JSON.relative_to(pathlib.Path.cwd())}")
