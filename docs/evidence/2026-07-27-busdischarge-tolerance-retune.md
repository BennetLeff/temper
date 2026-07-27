# BusDischarge resistor resize: worst-case tolerance derivation

**Date:** 2026-07-27
**Scope:** `elec/src/modules.ato::BusDischarge` (`r_dis1a/1b/2a/2b`).

## Falsifier (stated before implementing)

**"No E-series 5W wirewound resistor value between the existing 4.7k and
a lower value clears BOTH the capacitor's +20% tolerance AND the
resistor's own tolerance simultaneously, while keeping dissipation under
the 5W rating."**

**Did not fire.** `3.9k` (E24/E96, real Vishay AC05 part) clears both
tolerances stacked with ~3s of margin, and per-resistor dissipation rises
to 1.85W (37% of the 5W rating) -- comfortable headroom remains.

## Background

`docs/hardware/BUS_CAPACITANCE_DERIVATION.md` SS5: the existing 9.4k/
string (2x 4.7k) design gives `tau = 9.4k * 3600uF = 33.8s`, reaching <34V
in `1.61*tau ~= 54s` against the **<60s** target -- passing nominally.
SS5.1: at the bus capacitor's own **+20% tolerance** (verified against
`EKMQ251VSN182MA50S`'s DigiKey product page), `C=4320uF`, `tau=40.6s`,
`t=65.4s` -- **fails**. The decision, already taken upstream (SS5.3 of
that document): resize the discharge strings, not the bus capacitance.

## Derivation

Target: `<60s` at the capacitor's `+20%` tolerance (`C=4320uF`), holding R
at nominal first (matching the derivation doc's own method):

```
R_max = 60 / (1.6094 * 4320e-6) = 8630 ohm per string
```

The derivation doc's own recommendation stops here at `~8.6k` (2x 4.3k).
**This pass goes one step further**: the discharge resistor itself also
carries a tolerance (the existing AC05 family is `+/-5%`), and a real
board can see the capacitor at +20% AND the resistor at +5% at the same
time. Stacking both:

```
t(R_nominal) = 1.6094 * (R_nominal * 1.05) * (3600e-6 * 1.2)
```

| R_nominal (per string) | t at C+20% only | t at C+20% AND R+5% (stacked) | Verdict |
|---|---|---|---|
| 9.4k (2x 4.7k, existing) | 65.35s | -- (already fails at C-only) | FAILS |
| 8.6k (2x 4.3k, capacitor-tolerance-only answer) | 59.79s | **62.78s** | FAILS once R's own tolerance is added |
| **7.8k (2x 3.9k, chosen)** | 54.23s | **56.94s** | **PASSES**, ~3.1s margin |

**2x 4.3k was evaluated first and rejected** precisely because it repeats
the same class of error the capacitor derivation itself flagged: passing
against one tolerance source (capacitance) while silently assuming the
other component (the resistor) sits at its nominal value. `3.9k` is the
nearest standard 5% E-series step below 4.3k that clears both stacked.

Nominal-only (both R and C at nominal, for reference, not a pass
criterion): `tau = 7.8k * 3600uF = 28.08s`, `t = 45.19s`.

## Dissipation and relay contact stress at the new current

```
I = 170V / 7800 ohm = 21.8 mA   (was 18.1 mA at 9.4k)
P_total_per_string = 170^2 / 7800 = 3.705 W
P_per_resistor = 1.853 W        (37% of the 5W rating; was 1.54W/30.8%)
```

**Resistor margin retained**: 1.85W against a continuous 5W rating, and
this figure IS the peak (dissipation only falls as the bus discharges
from 170V, so there is no separate "pulse" event to check beyond this
steady-state-at-full-voltage number -- the resistor is rated for
continuous operation at 5W, and the discharge event is a slow, seconds-
long decay, not a fast pulse in the sense that would invoke a separate
pulse-power derating curve).

**Relay contact stress** (`modules.ato`'s `BusDischarge` module docstring,
verified 2026-07-16 against the Omron G5LE datasheet K100-E1-08): break
current rises from ~18mA to ~21.8mA, still two orders of magnitude below
the ~0.4A minimum arc-sustain current of Ag contacts (5.4% of that
threshold, same order of magnitude as before -- conclusion unchanged).
The out-of-catalog 170VDC break conclusion (max switching voltage 125VDC
per the datasheet) is independent of current and is also unchanged. The
RC snubber sizing (100R/470nF, dV/dt and closure-energy figures) depends
only on the snubber's own RC and the bus voltage, not on the discharge
string resistance, so those figures (6.8mJ, 1.7A peak, 47us tau) are
unaffected by this resize.

**Note on the task's line-number pointer**: the task referenced
`modules.ato:700-724` for "the relay contact stress conclusion." At HEAD,
lines 700-724 are `PowerInput`'s inrush *bypass* relay (`G4A-1A-E`, NO-
only), a different relay entirely from `BusDischarge`'s NC discharge
relays (`G5LE-1`). The actual contact-stress analysis lives in
`BusDischarge`'s own module docstring (verified above); line numbers have
shifted since the task was written, due to unrelated intervening commits
this session rebased across.

## Real part verification

**`AC05000003901JAC00`** (Vishay, 3.9 kOhm, +/-5%, 5W, axial 0.295"dia x
0.709"L) -- confirmed as an exact-match, active, orderable part via a
live DigiKey product search fetch (currently 0 stock, 25-week
manufacturer lead time, same as most passives in this BOM per the prior
BOM availability sweep -- not a blocker, consistent with existing parts).
Same Vishay AC05 series and footprint as the prior `AC05000004701JAC00`
(4.7k), so no footprint/package change.

## UNVERIFIED

- `AC05000003901JAC00`'s 25-week lead time and 0 current stock were
  observed at fetch time (2026-07-27) and may change; not independently
  cross-checked against a second distributor.
- Aging/endurance drift of the bus electrolytic capacitor over the
  product's service life is not modeled here (same caveat the
  capacitance derivation document already carries) -- this resize
  addresses the capacitor's rated tolerance, not long-term drift.
