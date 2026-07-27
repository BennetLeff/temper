# DC Bus Bulk Capacitance — Derivation From First Principles

**Date:** 2026-07-26
**Scope:** `C_BUS1`/`C_BUS1B` (upper half-bus) and `C_BUS2`/`C_BUS2B` (lower
half-bus), `elec/src/modules.ato:591-618`. **No files under `elec/`, `pcb/`,
or `docs/hardware/BOM.md` are modified by this document.** This is a
derivation to be reviewed, not a part swap.

**Read first, not re-derived here:**
`docs/evidence/2026-07-26-bus-capacitor-architecture-review.md` (no
derivation for 3600 µF exists; the cited simulation does not exist; every
electrolytic reselection route is board-area-infeasible) and
`docs/evidence/2026-07-26-bus-capacitor-ripple.md` (the installed part fails
rated ripple current 4.2–5.8×, central 4.8×, using an *assumed* 30–60°
conduction-angle range not derived from capacitance).

---

## 0. Falsifier, stated before deriving

*This derivation fails if the ripple-voltage ceiling that actually governs
safe operation turns out to be set by the resonant tank's power-transfer
function — i.e., by how much delivered power droops as the bus sags, and
whether that droop forces the switching frequency close enough to resonance
to erode the ZVS margin — because that function needs the tank's reflected
resistance (Q), and `TANK_COIL_SPECIFICATION.md` has already shown this
repo's only model of that (`pan_load.sub`) is ~10× wrong (implied Q of 143
against a realistic ~14).*

**Checked. Result: fires for two of the four candidate constraints named in
the task, and does not fire for the other two.** §3 below shows the
Coss-charging timing budget for ZVS (a real, dead-time-and-datasheet-driven
number) has roughly two orders of magnitude of margin regardless of bus
ripple, and IGBT/capacitor voltage ratings have 45–350% margin regardless
of ripple — neither depends on tank Q, and neither is binding. But whether
the tank can still deliver 1800 W (and hold `PWR-02`/`EFF-02`) through the
bottom of a wider ripple excursion **does** depend on the tank's V→P
transfer function, which needs Q. **That specific question is blocked**,
named precisely in §7.

---

## 1. What the ripple-voltage budget is *not* bounded by

Checked against real numbers before appealing to judgment, per the task's
instruction not to assume stiffness is required.

### 1.1 IGBT and capacitor voltage ratings — not binding

`q_high`/`q_low` are `IKW40N120H3`, 1200 V (`elec/src/modules.ato:77-83`).
Full bus differential is 340 V nominal, 390–410 V at the (currently
fail-open, see `docs/STRATEGY.md:563` — a separate, already-tracked defect
not touched here) OVP trip point. **Margin is ≥3× even at the absolute
maximum declared bus voltage (400 V,** `main.ato:50`**), before any ripple
consideration.** Ripple changes nothing here: it is a rating check against
peak voltage, and §1.3 below shows peak voltage does not move with
capacitance.

`c_bus1/1b/2/2b` are `EKMQ251VSN182MA50S`, 250 V (`modules.ato:591-618`).
Nominal half-bus peak is 170 V — **47% margin already, at zero ripple.**
Even a large ripple excursion (§4's tables reach 40%+ droop at very low C)
only ever *reduces* the trough below 170 V; it cannot push the part above
its 250 V rating, because droop is a downward-only perturbation from a peak
set by the line (§1.3).

### 1.2 ZVS margin, via the Coss-charging timing budget — not binding

This is the mechanism that actually connects bus voltage to ZVS: during
dead time, tank current must charge/discharge the switch-node capacitance
(both IGBTs' Coes in parallel) across the bus swing before the opposite
device turns on. Both real numbers used here are `elec/`-sourced or from a
manufacturer datasheet fetched directly, not modeled:

- `t_dead_time = 305.4ns` (34 kΩ `R_DT`, `BOM.md:23`, `main.ato:244`).
- `Coes = 185 pF typ.` at `Vce=25V, Vge=0V, f=1MHz` — Infineon `IKW40N120H3`
  datasheet Rev. 2.1 (2014-11-26), p.5, "Dynamic Characteristic" table,
  fetched directly. (Measured at 25 V; real Coes at the 170–400 V operating
  range is lower still, since junction depletion capacitance falls with
  reverse bias — using the 25 V figure at full bus voltage *overstates* the
  charge required, which is the conservative direction for this check.)

Total switch-node capacitance ≈ `2×185pF = 370pF`. Charge to swing the full
bus differential, using the OVP ceiling (410 V) as a deliberately extreme
upper bound covering essentially any ripple/tolerance scenario:

```
ΔQ = C × ΔV = 370pF × 410V = 151.7 nC
I_min = ΔQ / t_dead = 151.7nC / 305.4ns ≈ 0.50 A
```

Tank current is bounded at **35.4–40 A RMS** independent of the pan model
(`docs/evidence/2026-07-26-ocp01-vs-full-power-current.md`, from committed
CT ratio and burden resistor alone). **Even if only ~1% of that RMS current
is actually available and correctly directed at the exact switching
instant — a deliberately pessimistic assumption, since the true
instantaneous value is the piece that needs tank Q — that is still ~0.35–0.4
A, comparable to or above the 0.50 A required.** The realistic margin is
plausibly one to two orders of magnitude, not a near-miss. This budget does
not become tight anywhere in the ripple range this document considers (up
to ~40% droop moves ΔV by tens of volts, not the ~250 V range this margin
already absorbs).

**This rules out one of the two ZVS mechanisms.** It does not touch the
other: `TANK_COIL_SPECIFICATION.md` and the ZVS sweep
(`docs/evidence/2026-07-26-zvs-margin-sweep.json`) show collapse is driven
by switching-frequency-to-resonance ratio (`f_sw/f_res ≥ ~1.02`, design for
`≥1.05`), "almost entirely by frequency... not by pan coupling." Whether a
sagging bus forces the frequency-tracking loop toward a smaller ratio to
hold 1800 W is a power-transfer-function question — routed to §7, not
resolved here.

### 1.3 Peak bus voltage does not depend on capacitance — argued, not simulated

This doubler is a peak-charging circuit: each half-bus cap charges toward
the line's peak once per cycle and *sags* (droops) until the next peak
recharges it. **The declared `v_bus_nominal = 340V` (`main.ato:65`) is the
peak the caps charge to, not a mean with symmetric ripple around it.**
Reducing C widens the recharge conduction angle (§2) and lowers peak
recharge *current*, which if anything reduces source-impedance IR drop at
the charging instant — a smaller cap cannot charge to a *higher* peak than
today's. **Ripple from a smaller C is a downward-only effect on trough
voltage; it does not raise the ceiling §1.1 checks against.** No
source-impedance model is built here to quantify the (favorable) direction
precisely — flagged UNVERIFIED in §9, but the direction is standard
peak-rectifier behavior, not in dispute.

**Net of §1.1–§1.3: none of the three "hard" constraints named in the task
bounds how far C can be reduced.** The only real ceiling found is
`BusDischarge` (§5), and the only reason not to reduce C arbitrarily far is
§7's blocked question.

---

## 2. Derivation: charge balance for the doubler's own recharge interval

**The interval is not a full-wave rectifier's.** Each half-bus bank
recharges once per full 60 Hz line cycle (`D1` conducts only on
`AC_L>AC_N`, `D2` only on the opposite half-cycle — `docs/evidence/
2026-07-26-bus-capacitor-ripple.md` §2, established there and used as-is).
**T = 1/60 Hz = 16.667 ms**, not the 8.33 ms a full-wave bridge would give.

**Charge-balance model** (standard capacitor-input filter approximation —
rectangular/linear discharge, constant `I_dc` load, no bench/SPICE
validation for this specific front end, flagged as such):

```
ΔV = I_dc,half × (1-δ) × T / C        [discharge, fraction (1-δ) of T]
r  = ΔV / V_peak                       [V_peak = 170V, the half-bus peak]
θ  = 2·arccos(1-r)                     [conduction angle, standard
                                         peak-rectifier geometry: cap
                                         voltage V_peak(1-r) is caught by
                                         the rising sinusoid at electrical
                                         angle θ/2 before the peak]
δ  = θ / 2π
```

This closes the loop the ripple doc left open (its own §4.1 in the
architecture review: "no validated model connecting a specific capacitance
value to a specific conduction angle... treated θ as an assumed
'industry-typical' range"). It is solved self-consistently (iteratively;
`r` and `δ` depend on each other) for a given `C`.

**Cross-check against the existing ripple doc:** at the *current* `C=3600µF`
(central case, η=0.90), this model gives `θ=59.9°, δ=0.166` — the ripple
doc *assumed* `θ=40°` for the same case. The two are in the same regime
(same order of magnitude, both well inside the doc's stated 30–60° "typical"
band) but not identical, because the doc's number was an industry-typical
assumption and this one is derived from the actual C. Both approaches
independently conclude the current design fails (§4).

---

## 3. Ripple current at derived C — the load-bearing finding

Computed for the doubler's three scenarios from the ripple doc (best
η=0.92/I_tank=35.4A, central η=0.90/I_tank=35.4A, worst η=0.85/I_tank=40A),
using the closed-form geometric model above for the LF (60 Hz) term and the
ripple doc's own unchanged HF (35 kHz) term
(`I_HF,group = I_tank,rms/√2`, divided — not multiplied, corrected during
this derivation — by `FM(35kHz)=1.49` to reach the 120 Hz-equivalent basis,
since the datasheet's multiplier >1 at high frequency means the part
tolerates *more* actual current there for the same heating). Full script:
`/private/tmp/.../scratchpad/buscap.py` (ephemeral, not committed).

| C (µF) | r (ripple, central) | ΔV (V) | LF group, 120Hz-eq (A) | HF group, 120Hz-eq (A) | Combined group (A) | Per-cap, N=2 (A) | Margin vs 2.70A rated |
|---|---|---|---|---|---|---|---|
| 4700 (withdrawn reselection) | 10.5% | 17.8 | 16.93 | 16.80 | 23.85 | 11.93 | **4.42×** |
| **3600 (current, installed)** | 13.4% | 22.7 | 15.73 | 16.80 | 23.01 | 11.51 | **4.26×** |
| 3300 | 14.4% | 24.6 | 15.35 | 16.80 | 22.76 | 11.38 | 4.21× |
| **3000 (this doc's recommendation)** | 15.7% | 26.8 | 14.95 | 16.80 | 22.49 | 11.24 | 4.16× |
| 2000 | 22.5% | 38.3 | 13.31 | 16.80 | 21.43 | 10.72 | 3.97× |
| 1000 | 40.5% | 68.9 | 10.81 | 16.80 | 19.97 | 9.99 | 3.70× |
| 470 | 72.3% | 122.9 | 8.42 | 16.80 | 18.79 | 9.40 | 3.48× |
| **C → 0 (mathematical floor)** | — | — | → 0 | 16.80 | **→ 16.80** | **→ 8.40** | **→ 3.11× (still failing)** |

**Reading this table is the central result of the derivation.** The HF
(35 kHz) term is *structurally independent of bulk capacitance* — it comes
from tank current splitting between the two half-bus banks each half-cycle,
not from how much capacitance is there. Because the two terms combine in
quadrature (`sqrt(LF² + HF²)`), and HF (16.80 A) already exceeds LF (15.73
A) at today's C, **shrinking C toward zero can mathematically buy back at
most `(23.01−16.80)/23.01 ≈ 27%`** of today's combined current — and that
floor requires an infinitely large, physically absurd ripple voltage to
approach. At the recommended 3000 µF the actual gain is **~2.3%** (4.26×→
4.16×). At even a 72%-ripple, 470 µF extreme, the gain is still only ~18%.

**Capacitance value is not the lever that fixes the ripple-current
failure.** This directly qualifies the architecture review's §4.1
hypothesis ("a smaller bulk capacitance... directly reduces RMS ripple
current per amp delivered") — true in isolation for the LF term, checked
here and confirmed, but swamped by the C-independent HF term once combined.
Fixing the ripple-current failure requires the architecture review's
already-identified, separate levers: a correctly-placed film HF bypass
(§3.2 there, ~819 µF/half at `hv_plus↔gnd_ref` / `gnd_ref↔hv_minus`) and/or
more or better-rated parallel electrolytic capacity (a genuine part search,
out of scope for a capacitance-*value* derivation and for this round's "no
`elec/src` or `BOM.md`" constraint).

---

## 4. The ripple-voltage budget, stated

Given §1 (nothing hard bounds C from below in the range considered) and §3
(C is not the ripple-current lever, so there is no reward for pushing it
far down), **the operative constraint on C is `BusDischarge` (§5), not a
ripple-voltage number chosen for its own sake.** The budget adopted here:

> **Reduce C only as far as `BusDischarge`'s safety margin under real
> component tolerance requires, and no further — because further reduction
> buys negligible ripple-current benefit (§3) while raising ripple voltage
> into a range (§7) this project cannot yet verify against ZVS/power
> delivery.**

This resolves to **~15–16% ripple (central case)** at the recommended
value, up from an implied ~13% at today's (also un-derived) 3600 µF —
a modest increase, not the large one an aggressive ripple-current chase
would have demanded, precisely because §3 shows that chase doesn't pay off.

---

## 5. `BusDischarge` — the actual governing constraint, and a new finding

`BusDischarge` (`modules.ato:762-981`): two relay-switched strings, 2×
4.7 kΩ/5 W wirewound in series per half-bus = **9.4 kΩ per string**
(`modules.ato:766-776`). Sizing per the module's own docstring:
`τ = 9.4kΩ × 3600µF = 33.8s`; 170 V → <34 V in `1.61τ ≈ 54s` against the
**<60s** target (`ln(170/34) = ln(5) = 1.6094`, matching the docstring's
1.61 figure). **Passes today, on ~9–10% nominal margin.** (Separately
confirmed: this <60s requirement exists only as comments in `modules.ato`
lines 445/636/773 and does not appear in `FUNCTIONAL_TEST_CRITERIA.md` —
a safety-relevant timing spec that never reached the requirements doc.)

### 5.1 New finding: the nominal margin does not survive real tolerance

`EKMQ251VSN182MA50S` is rated **±20% capacitance tolerance** — verified by
fetching the DigiKey product page directly (`digikey.com/en/products/
detail/united-chemi-con/EKMQ251VSN182MA50S/758193`, "Tolerance" field),
not assumed. At the top of that band:

```
C_worst = 3600µF × 1.2 = 4320µF
τ_worst = 9.4kΩ × 4320µF = 40.6s
t_worst = 1.6094 × 40.6s = 65.4s   >  60s target — FAILS
```

**The currently-installed design already has no real margin against its own
parts' tolerance spec** — a distinct, previously-unquantified finding from
this derivation, independent of the ripple-current failure and independent
of whatever C value is ultimately chosen. (Aging was not modeled — 2000 h
life rating and typical electrolytic capacitance drift over life are a
separate, unaddressed question, flagged in §9.)

### 5.2 Ceiling on C from this constraint

Solving for the largest nominal C whose **worst-case (+20%) tolerance**
discharge still clears 60 s:

```
C_nominal ≤ 60s / (1.6094 × 9400Ω × 1.2) ≈ 3303 µF
```

Targeting the same ~9% cushion the current design has *nominally* today,
but now guaranteed at worst-case tolerance:

```
C_nominal ≈ 54.5s / (1.6094 × 9400Ω × 1.2) ≈ 2999 µF  →  recommend 3000 µF
```

At 3000 µF nominal, worst-case (+20%) tolerance gives `C=3600µF,
τ=33.8s, t=54.4s` — **exactly today's nominal-case number, now as the
worst case.** Real margin restored.

### 5.3 An equally valid alternative: resize the discharge resistors instead

`BusDischarge`'s timing is `τ = R × C`; either factor can move it. Reducing
the two series 4.7 kΩ resistors per string to **~4.3 kΩ each (8.6 kΩ per
string)** achieves the same worst-case-tolerance safety margin **without
changing capacitance at all**:

```
R_max = 60s / (1.6094 × 4320µF × 1.2) ≈ 8632Ω  →  8.6kΩ (2× 4.3kΩ)
```

Since §3 shows capacitance value does not meaningfully fix ripple current
either way, **this is arguably the lower-risk fix**: it touches only two
resistor values (already-costed part family, no new MPN, no board-area
change, no interaction with the ripple-current problem) rather than an
electrolytic capacitor re-selection. Steady-state dissipation per resistor
rises modestly (`170²/8.6k/2 ≈ 1.68W` vs today's `1.54W`, both well under
the 5 W rating with room to spare). This document's primary deliverable is
still the capacitance derivation asked for, but this alternative is real
and should be weighed against it.

---

## 6. Reality checks

### 6.1 Real parts

**No new MPN is proposed or fabricated here.** A 3000 µF/half target,
realized as 2× ~1500 µF/250 V units in the same `CP_Radial_D35.0mm_
P10.00mm_SnapIn` footprint class as the existing, verified
`EKMQ251VSN182MA50S`, is plausible (electrolytic families commonly offer
several capacitance steps at a fixed can diameter) but **UNVERIFIED — no
distributor page for a specific ~1500 µF/250 V D35 snap-in part was fetched
in this pass.** That search is the necessary follow-up before any BOM
change, and is explicitly out of scope here (hard constraint: no `elec/src`
or `BOM.md` edits this round). The §5.3 resistor-only alternative requires
no new part at all — `AC05000004701JAC00`-class 4.3 kΩ/5 W wirewound parts
are the same family already on the BOM at 4.7 kΩ.

### 6.2 Board area

**Zero impact**, by construction — the recommendation does not change can
diameter or count (still 2 per half-bus, same D35 footprint class), unlike
the withdrawn reselection that the architecture review closed off (6× 66mm
cans at 82.7% of the 152×234mm board, or 20–24 D35 cans at 90–108%). The
existing four cap positions and their 11–18mm neighbor clearances are
undisturbed. The §5.3 resistor alternative has zero board-area impact by
definition (same resistor package, different value).

### 6.3 `BusDischarge` (the joint trade, per §5)

Already solved together in §5: **reducing C from 3600→3000 µF/half moves
`BusDischarge`'s worst-case-tolerance discharge from 65.4s (failing) to
54.4s (passing, restoring the original nominal-case margin)** — this is a
strict improvement on this axis, not a trade against it, because both the
ripple-current problem (§3, structurally unfixable by C) and the discharge
problem (§5, fixable by lowering C) point the same direction: **less C, not
more.** There is no tension between them once §3's finding is taken
seriously; the withdrawn reselection's original C-increase direction was
wrong on both counts simultaneously, which is consistent with why it also
failed on board area.

### 6.4 Does the ripple-current failure actually resolve at 3000 µF?

**No.** Per §3's table: margin moves from 4.26× to 4.16× — a ~2.3%
improvement, not a fix. The design remains **>4× over the rated ripple
current at the recommended value.** This must be closed separately, via the
architecture review's film-bypass and/or parallel-count/rating levers, not
by this capacitance change.

---

## 7. Blocked: does 3000 µF's ~16% ripple stay inside what the tank/firmware need?

**Named precisely, per the task's instruction that a withheld value with a
stated blocker is a better result than a confident number on an uncalibrated
model.**

The one question this derivation cannot close: does a bus that sags ~16%
below peak once per line cycle still let the frequency-tracking loop hold
1800 W (`PWR-02`: ±5% @1800W, `EFF-02`: >92% @1800W) without needing to
detune close enough to resonance to erode the ZVS margin
(`TANK_COIL_SPECIFICATION.md`'s `f_sw/f_res ≥ ~1.05` recommendation)? That
requires the tank's `P(V_bus, f_sw)` transfer function, which requires the
tank's reflected resistance/Q — exactly the number
`TANK_COIL_SPECIFICATION.md` shows this project's only model gets ~10×
wrong (implied Q of 143 against a realistic ~14).

**The measurement that would unblock this, named precisely:** bench-measure
(or otherwise properly parameterize) the real coil-and-pan magnetic
coupling and reflected resistance — the same calibration
`TANK_COIL_SPECIFICATION.md` already names as its own blocker — then
re-evaluate `P(V_bus, f_sw)` across the ripple excursion this document
derives (170V trough at 3000µF central case ≈ 143V, i.e., an 27V/16% sag
each line cycle) to confirm `PWR-02`/`EFF-02` and the ZVS margin both hold
at the bottom of that sag. Until that measurement exists, **the 3000 µF
recommendation is offered as the value that best satisfies the constraints
this project *can* check (§1, §3, §5) — not as a value proven safe against
the one constraint it cannot yet check.**

---

## 8. Commercial sanity check

Hsieh, "Study of half-bridge series-resonant induction cooker powered by
line rectified DC with less filtering," *IET Power Electronics* (2023) —
already cited in the architecture review, re-confirmed here via direct
search: a 3 kW half-bridge series-resonant cooker (same topology class)
achieves **0.95–0.995 power factor from 300 W–3 kW** via frequency control
(24.7–50.6 kHz) specifically *because* of reduced DC-bus filtering, stating
the general principle: "a low value of filter capacitor is chosen to get a
high power factor, and as a consequence, a high-ripple DC bus is obtained."
The full paper (IET Digital Library, ResearchGate) returned HTTP 403 on
direct fetch — **UNVERIFIED: this paper's own specific capacitance value or
ripple percentage**, not obtained. What is confirmed (search result
abstract) is the qualitative design philosophy and the PF/frequency-range
figures above, which is enough to say: **a published, real design in this
exact topology class embraces *more* ripple than this document
recommends, not less** — the ~16% figure here is a conservative move
relative to that precedent, not a risky one.

A separate attempt to find a concrete commercial teardown capacitance value
(Kaizer Power Electronics' 8kW induction cooktop teardown) returned "4 µF"
for DC bus capacitance — **not used**: this is implausibly small for bulk
storage on a multi-kW half-bridge and far more consistent with a
bypass/film value or a transcription artifact than a bulk-storage figure,
and no follow-up source could confirm which. Flagged UNVERIFIED rather than
cited as support.

---

## 9. UNVERIFIED

| Item | Reason |
|---|---|
| **Whether 3000 µF (or any C in the range this document considers) keeps `PWR-02`/`EFF-02`/ZVS margin intact through the bottom of the ripple sag** | Needs the tank's `P(V_bus,f_sw)` transfer function → needs tank Q → needs the coil/pan calibration `TANK_COIL_SPECIFICATION.md` already shows is missing. Named as the blocking measurement in §7. |
| A specific real MPN for a ~1500 µF/250 V D35-class part | No distributor page fetched for this value in this pass; explicitly out of scope (no `elec/src`/`BOM.md` edits this round). Do not treat "2× ~1500µF" as a specified part. |
| Exact sensitivity of doubler peak charging voltage to capacitance (§1.3) | Argued from standard peak-rectifier behavior, not quantified with a source-impedance model. Direction (favorable or neutral, never adverse) is not in dispute; magnitude is. |
| Electrolytic capacitance drift with age/life, beyond the ±20% initial-tolerance figure used in §5.1 | Datasheet gives ΔC ≤±20% as an *endurance pass/fail* criterion at 2000h/105°C/rated conditions, not a drift-vs-time curve; not modeled. |
| Hsieh (2023)'s own specific bus capacitance value or ripple percentage | Paper is paywalled; IET Digital Library and ResearchGate both returned HTTP 403 on direct fetch. Only the abstract-level PF/frequency-range figures and the quoted design-principle sentence are used, both already independently corroborated in the architecture review. |
| The "4 µF" Kaizer Power Electronics teardown figure | Fetched but not trusted — implausible for bulk storage at multi-kW; not used as evidence either way. |
| OVP-01's fail-open condition (`docs/STRATEGY.md:563`) | Noted in §1.1 as context only — it is a wiring defect unrelated to and unaffected by any capacitance value discussed here. Not this document's fix. |
| `docs/specs/REQUIREMENTS.md` REQ-PWR-01/02 | Describes a single-170V-bus, full-wave-rectified topology inconsistent with the actual doubler design (±170V about a grounded midpoint) — not used as a source anywhere in this derivation, consistent with the architecture review's finding that this document's capacitance figure is self-asserted with no formula. |

---

## 10. Recommendation

**Reduce nominal bulk capacitance from 3600 µF/half to ~3000 µF/half
(±20%-tolerance-class part, same D35 snap-in footprint family), OR
equivalently resize `BusDischarge`'s per-string resistance from 9.4 kΩ to
~8.6 kΩ and leave capacitance unchanged (§5.3) — both close the newly-found
tolerance gap in `BusDischarge` (§5.1) with zero board-area impact.**

**Do not expect either move to resolve the ripple-current failure.** §3
shows capacitance value has, at best, a mathematically bounded ~27% effect
on combined ripple current and the practical effect in the range considered
here is a few percent — the failure is dominated by the C-independent
35 kHz term and needs the architecture review's film-bypass and/or
parallel-capacity fixes instead.

**Blocked, and named:** whether the resulting ~16% ripple voltage is safe
for power delivery and ZVS margin at full power requires the coil/pan
coupling measurement `TANK_COIL_SPECIFICATION.md` already identifies as
missing (§7). This recommendation should be treated as provisional on that
measurement, not as a closed spec.
