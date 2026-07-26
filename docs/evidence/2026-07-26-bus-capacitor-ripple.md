# Bus capacitor ripple current: does `EKMQ251VSN182MA50S` survive this design?

**Scope:** `C_BUS1/1B/2/2B`, 4× 1800 µF/250 V United Chemi-Con KMQ, 2 parallel
per half-bus (`elec/src/modules.ato:521-548`, `BOM.md:52`). No files under
`elec/`, `pcb/`, or the BOM were modified to produce this document.

**Falsifier (`METHODOLOGY.md` §5):** *this analysis fails if the 120 Hz-band
doubler-recharge current, computed from input power alone, does not already
exceed the datasheet rating by a wide margin — because then the verdict would
hinge on the 35 kHz tank current, which the undefined coil inductance
(`TANK_COIL_SPECIFICATION.md`) prevents deriving directly.* **Checked: false.**
The low-frequency term alone clears the rated current 2.8–4.2× before the
switching term is added — the verdict does not depend on the unresolved tank.

---

## 1. Datasheet ratings, with conditions

Source: United Chemi-Con **CAT. No. E1001E**, KMQ Series (downsized snap-ins,
105°C). `EKMQ251VSN182MA50S` is listed explicitly: 250 V row, 1800 µF, φ35×L50.

| Parameter | Value | Condition (as printed) |
|---|---|---|
| Rated capacitance | 1800 µF | 20°C, 120 Hz |
| Rated voltage | 250 Vdc | — |
| Dissipation factor tanδ (max) | 0.15 | 20°C, 120 Hz, 160–250 Vdc group |
| **Rated ripple current** | **2.70 Arms** | **105°C, 120 Hz** |
| Endurance (load life) | **2000 h at 105°C**, rated ripple + rated V | pass: ΔC ≤±20%, tanδ ≤200% initial, leakage ≤ initial spec |
| Category temp range | −25 to +105°C | — |

**Frequency multipliers** (160–250 Vdc column), applied to the 120 Hz rated
current to find the allowed current at another frequency:

| Hz | 50 | 120 | 300 | 1k | 10k | 50k |
|---|---|---|---|---|---|---|
| Multiplier | 0.81 | 1.00 | 1.17 | 1.32 | 1.45 | 1.50 |

**Derived ESR** (not printed directly): `ESR=tanδ/(2πfC)` at 120 Hz/20°C/max
tanδ → `0.15/(2π·120·1800µF) ≈ 0.111 Ω`. No ESR at 35 kHz, no ESR matching
tolerance, no thermal resistance (Rth) is published — flagged UNVERIFIED in
§9; none are needed for the headline comparison, which the frequency
multipliers already handle. **No temperature-vs-ripple derating table and no
life-vs-temperature formula appear anywhere in this datasheet** — both used
in §7 are generic industry approximations, clearly labeled as such.

---

## 2. Topology and the frequency actually present

`PowerInput` (`modules.ato:418-690`) is a **Delon (cascade) voltage doubler**,
not a bridge-plus-single-cap filter: `D1` conducts only when `AC_L>AC_N`,
charging `C_BUS1`(+`1B`) to +170 V vs. the doubler midpoint (`gnd_ref`,
hard-wired to `AC_N`); `D2` conducts only the opposite half-cycle, charging
`C_BUS2`(+`2B`) to −170 V. **Each bank recharges once per full 60 Hz cycle,
not twice** — standard doubler behavior, and it differs from the task brief's
"120 Hz" framing (which describes a bridge-plus-single-cap filter). I use the
physical rate, 60 Hz, and flag the deviation.

`HalfBridge` (`modules.ato:238-385`) draws from `C_BUS1` while `Q_high`
conducts, from `C_BUS2` while `Q_low` conducts, tank returning to `gnd_ref` —
each half-bus bank alone supplies the tank current for its half of the
~35 kHz switching cycle.

---

## 3. Low-frequency (mains-recharge) component

| # | Assumption | Value used | Basis |
|---|---|---|---|
| A1 | `P_in = P_out/η` | `P_out=1800W` | `main.ato:81` |
| A2 | Efficiency η | 0.90 central (0.85–0.92 bounds) | `main.ato:88` `eta_min=0.90`, `assert >=0.85`; STRATEGY EFF-02 target 92% (unmeasured — "0 of 22 gates measured") |
| A3 | Half-bridge splits avg power 50/50 between rails | exact 50/50 | symmetric square-wave drive into symmetric tank |
| A4 | Recharge pulse shape | rectangular, conduction angle θ | standard cap-input-filter approximation; no bench/SPICE data for this front end |
| A5 | Conduction angle θ | 40° central (30–60° bounds) | typical range for cap-input rectifiers; steady-state source Z here is low (NTC bypassed post-startup, CMC ≈7.1mΩ), favoring the low end — not bench-verified |

**Derivation:** for a bank supplying constant `I_dc` between rectangular
recharge pulses of duty `δ=θ/360°`, charge balance gives peak current
`I_p=I_dc/δ` and RMS ripple `I_ripple,rms = I_dc·sqrt((1−δ)/δ)`.
`I_dc,half = (P_in/2)/170V` (per half-bus bank, both parallel caps).

| η | θ | I_dc,half | δ | factor | Ripple, group (A) | Ripple, per cap (A) |
|---|---|---|---|---|---|---|
| 0.90 | 40° | 5.88 | 0.111 | 2.828 | 16.64 | 8.32 |
| 0.92 | 60° | 5.75 | 0.167 | 2.236 | 12.87 | 6.43 |
| 0.85 | 30° | 6.23 | 0.083 | 3.317 | 20.66 | 10.33 |

Actual ripple is ~60 Hz, not 120 Hz; datasheet has no 60 Hz point, so
log-interpolate 50 Hz (0.81) / 120 Hz (1.00) → **FM(60Hz)≈0.837**. Dividing
per-cap currents by 0.837 gives the 120 Hz-equivalent LF term used in §5:
**9.94 / 7.69 / 12.34 A** (central/best/worst).

---

## 4. High-frequency (~35 kHz switching) component

**Blocking issue:** `L_TANK` has no committed inductance
(`TANK_COIL_SPECIFICATION.md`; STRATEGY's "ZVS margin" finding: resonance is
undetermined). This blocks deriving the 35 kHz tank current from tank values.

**What's still usable:** `STRATEGY.md` ("OCP-01 vs. full-power tank current",
`docs/evidence/2026-07-26-ocp01-vs-full-power-current.md`) already establishes,
from committed CT ratio and burden resistor alone (no pan model, no
inductance), that 1800 W requires tank RMS current in the **35.4–40 A** band
(35.4 A = as-built OCP-01 trip converted to RMS; 40 A = its cited "typical
1.8 kW hob"). Used here as an externally-sourced bound, not re-derived.

**A6:** each bank carries tank current only while its switch conducts (~half
the period, sinusoidal, no dead-time overlap) → for a sinusoid gated on one
half-cycle per period, `I_cap,rms = I_tank,rms/√2` per bank, `/2` again for
equal sharing → **per-cap factor 0.3536 × I_tank,rms**.

| I_tank,rms | Per-cap actual | FM(35kHz, interp.) | Per-cap 120Hz-equiv |
|---|---|---|---|
| 35.4 A | 12.52 A | 1.49 | 8.40 A |
| 40.0 A | 14.14 A | 1.49 | 9.49 A |

FM(35kHz) log-interpolated between 10kHz (1.45) and 50kHz (1.50) → **1.49**;
the whole 1.45–1.50 range changes the result <3%, immaterial to the verdict.

---

## 5. Combined ripple current vs. rating

Components at different frequencies add in quadrature, each already at its
120 Hz-equivalent (§3, §4):

| Scenario | LF equiv (A) | HF equiv (A) | Combined (A) | Rated (A) | **Margin** |
|---|---|---|---|---|---|
| Best (η=0.92, θ=60°, I_tank=35.4A) | 7.69 | 8.40 | 11.39 | 2.70 | **4.22×** |
| Central (η=0.90, θ=40°, I_tank=35.4A) | 9.94 | 8.40 | 13.02 | 2.70 | **4.82×** |
| Worst (η=0.85, θ=30°, I_tank=40A) | 12.34 | 9.49 | 15.57 | 2.70 | **5.77×** |

**Under every combination checked — including the one most favorable to the
design — per-capacitor ripple current is 4.2–5.8× the rated 2.70 Arms.** No
ESR-matching or sharing assumption closes a gap this large.

---

## 6. Parallel-pair sharing

All figures assume **ideal 50/50 current sharing** between the two 1800 µF
units per half-bus. The datasheet publishes no ESR tolerance or matching spec,
so this is best-case, not verified. Sharing degrades with ESR mismatch (unit
tolerance, lot variation, or differential heating — a hotter cap's ESR rises,
pulling more shared current onto it, a positive-feedback direction). Any real
mismatch makes §5's margins **worse**, never better.

---

## 7. Temperature and life

`t_ambient_max=323.15K` (50°C, `main.ato:77`); caps sit near a heatsink per
the brief, but no bus-cap hotspot temperature is modeled or measured anywhere
in this repo — **UNVERIFIED beyond "≥50°C chassis ambient."**

The 2.70 A rating is already specified **at the 105°C category max** — no
derating table exists either direction in this datasheet, so 50°C ambient does
not, by itself, buy back the 4.2–5.8× overage above.

**Self-heating from the overcurrent is the dominant unknown.** At ~4.8× rated
current, I²R dissipation rises ~4.8²≈23× vs. the datasheet's own rated-current
point, but Rth to convert that to a ΔT is not published. **UNVERIFIED: exact
hotspot temperature** — qualitatively, a 23× dissipation increase on a part
already rated at the top of its temperature category is very unlikely to stay
under 105°C.

**Life model, run as asked, precondition flagged:** this datasheet publishes
no life-vs-temperature formula — only "2000 h at 105°C, rated ripple current."
The generic industry rule (life doubles per 10°C below rated max; not sourced
from this datasheet) gives, **if operated at or below rated current:**

```
L(50°C) = 2000h × 2^((105−50)/10) = 2000h × 45.25 ≈ 90,500 h (≈10.3 years)
```

**This number does not apply here** — it assumes operation within rated
current; §5 shows 4.2–5.8× that current, a regime the doubling rule was never
meant to model. **UNVERIFIED: quantified life under the as-designed
overcurrent condition** — expect a fraction of 90,500 h, plausibly a rapid
field failure (venting from sustained over-temperature) rather than a merely
shortened life. No number is fabricated for that case.

---

## 8. Verdict

**FAILS.** Across η 0.85–0.92, θ 30–60°, tank current 35.4–40 A RMS,
per-capacitor ripple current is **4.2×–5.8× (central 4.8×)** the rated
2.70 Arms. The falsifier does not hold: the low-frequency component alone
(2.8–4.2× rated) already fails the design, independent of the undefined tank
inductance; the switching component and the inapplicable life model only
worsen it. `BOM.md`'s "2x 2.7A@120Hz ripple rating per half"
(`modules.ato:526`) is nameplate arithmetic (2×2.70A=5.40A) with no load
calculation behind it — this document is that missing calculation.

**Not evaluated here (out of scope):** more parallel capacitors, a
higher-ripple-rated part, or active PFC ahead of the doubler to remove the
high-crest-factor charging driving §3.

---

## 9. UNVERIFIED items

| Item | Reason |
|---|---|
| ESR at 35 kHz | Not published in E1001E; not needed for the headline comparison |
| ESR unit-to-unit matching tolerance | Not published |
| Thermal resistance (Rth), D35×L50 case | Not published in the pages retrieved |
| Actual tank/coil current at 35 kHz | `L_TANK` undefined; used repo's OCP-01-derived 35.4–40A bound instead |
| Converter efficiency (actual, bench) | 0.90/0.85/0.92 are design targets/asserts, none measured |
| Conduction angle θ | No bench/SPICE data for this front end; industry-typical range used |
| Life-vs-temperature formula | Not published in this datasheet; generic rule applied and flagged |
| Bus-cap case/hotspot temperature | Only chassis `t_ambient_max=50°C` asserted; no cap-specific thermal model |
| Life under the as-derived overcurrent condition | No formula available; not fabricated |
