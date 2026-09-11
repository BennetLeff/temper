# Buck margin resolution proposal — 2026-09-10

This is a review proposal for the parent audit. It deliberately does not edit
the authoritative requirements, BOM, approved registry, PCB, or circuit gate.
The numbers below separate engineering acceptance criteria from manufacturer
guarantees and identify the measurements or vendor curves still needed.

## Candidate requirements for parent review

These are review inputs only; the parent must decide whether any become
requirements:

* A proposed 125 mV board ripple criterion is **rejected as a closure
  criterion pending an upstream source/system ripple budget**. It remains only
  as a labeled engineering sensitivity point over 13.5, 15.0, and 16.5 V,
  at both 0.5 A continuous and 1.0 A / 10 ms
  pulse endpoints. Use a 20 MHz measurement bandwidth and a spring ground.
  This is an unapproved Temper engineering proposal, not a supported upstream
  limit and not a TI limit.
* Use **4.54 uF as a C9 effective-capacitance sensitivity assumption** for the initial
  sensitivity run. This is a deliberately conservative engineering input
  (retained audit approximation `~7 uF × 0.90 temperature × 0.90 tolerance ×
  0.80 aging`), not a Samsung guaranteed minimum. It cannot by itself close
  any VIN-ripple requirement.
* Keep C10 and C13 at **64 nF each as an effective-capacitance sensitivity
  assumption** as a transparent
  sensitivity input only. No exact-part bias/temperature curve was retained;
  the value is 100 nF × 0.90 tolerance × 0.90 temperature × 0.80 aging.
  It is not a manufacturer guarantee. C10 is the bootstrap capacitor and
  should also be checked against TI's 0.1 uF recommendation on the assembled
  board.
* Model C11 and C12 at **11.00 uF each as an effective-capacitance sensitivity
  assumption** (22.00 uF total)
  for transient sensitivity. This uses Murata's retained 15.288456 uF minimum
  at 3.465 V / 10 mVrms, multiplied only by 0.90 tolerance and 0.80 aging;
  the retained temperature trace already contains temperature variation.
  This remains a reviewed model input, not a combined-condition guarantee.
* **1.60 A peak** is only a nominal-500-kHz normal-operation screen. TI's
  specified 450-kHz low corner and L=4.48 uH produce 1.62–1.65 A at 1 A
  output across VIN; a rounded **1.70 A** screen is a candidate pending review.
* Keep **8.35 A at 105 °C** visible as the existing fault criterion. Whether it
  belongs in the initial harness milestone or a later fault-robustness
  milestone is a **scope-change proposal awaiting parent review**. It is 1.25 ×
  the 6.68 A converter fault-current ceiling, not a normal-load requirement.

TI's official LMR51430 datasheet recommends a high-frequency input capacitor
of 4.7 uF or higher, X5R/X7R, with voltage rating approximately twice maximum
VIN; its worked 3.3 V example uses two 4.7 uF / 50 V parts and approximately
10 mOhm ESR. It separately recommends 0.1 uF for high-frequency filtering and
uses two 22 uF output capacitors. These are device/application recommendations,
not a 125 mV board-ripple guarantee: [TI LMR51430 datasheet](https://www.ti.com/lit/ds/symlink/lmr51430.pdf).

## C9 ripple calculation

For a buck input capacitor, use `D=3.3/VIN` and
`dV_C = IOUT*D*(1-D)/(fSW*Ceff)`. TI specifies the 500-kHz trim as 450–560
kHz, so 450 kHz and L=4.48 uH are the ripple-stressing corners. ESR ripple is
an edge step, not an RMS heating term; use the conservative envelope
`I_L,peak = IOUT + dI/2`, `dV_ESR = I_L,peak × ESR`. The retained replay
source model uses **100 mOhm**. TI's approximately 10 mOhm figure is its
example capacitor ESR, not an upstream source guarantee.

| VIN | D | C ripple @ 0.5 A | C+ESR @ 0.5 A | C ripple @ 1 A | C+ESR @ 1 A |
|---:|---:|---:|---:|---:|---:|
| 13.5 V | 0.2444 | 45.2 mV | 56.4 mV | 90.4 mV | **106.6 mV** |
| 15.0 V | 0.2200 | 42.0 mV | 53.4 mV | 84.0 mV | 100.4 mV |
| 16.5 V | 0.2000 | 39.2 mV | 50.7 mV | 78.3 mV | 94.9 mV |

These columns use 450 kHz and 4.48 uH at VOUT=3.3 V and include only the
10 mOhm capacitor ESR edge term. The 100 mOhm replay source resistance cannot
be added as `I_L,peak × R`: it is upstream of C9 and its contribution depends
on the source, wiring, capacitor ESL/ESR, and switching time. Resolve it with
an RLC time-domain model or the assembled VIN-pin measurement; no additive
source total is claimed here. At VOUT=3.465 V, the corresponding 1 A totals
are 109.8, 103.6, and 98.0 mV.

The low VIN / high load corner dominates because `D(1-D)` is largest there.
At a 50 mV board budget, the ideal C-only requirement is 8.21 uF at 450 kHz
and 13.5 V / 1 A; allowing a 16 mV ESR edge term requires about 11.2 uF.
C9's 4.54 uF sensitivity assumption cannot support 50 mV by calculation. No
supported source or TI number selects 125 mV, so it is rejected as a closure
criterion pending the upstream/system budget.
Measure the assembled VIN waveform and source impedance before deciding on
extra capacitance or a budget change.

## Effective-capacitance envelopes

| Ref(s) | Nominal | Retained exact evidence | Proposed sensitivity assumption | Status |
|---|---:|---|---:|---|
| C9 Samsung CL32B106KBJZW6E | 10 uF | Retained audit approximation ~7 uF at 16.5 V | 4.54 uF | sensitivity input; measure combined corner |
| C10, C13 KEMET C0603C104K5RACTU | 100 nF each | Exact MPN, 50 V X7R, ±10%; no retained bias curve | 64 nF each | explicit placeholder, not guaranteed |
| C11, C12 Murata GRM32ER71E226KE15L | 22 uF each | 15.288456 uF retained minimum at 3.465 V; 25 °C bias trace and temperature trace | 11.00 uF each | sensitivity assumption, not guarantee |

For C9, retain the audit's approximate `~7 uF × 0.90 × 0.90 × 0.80 ≈ 4.54
uF`; do not present the approximate source point as precision data. For C11/C12,
15.288456 × 0.90 × 0.80 = 11.00768832 uF; use 11.00 uF conservatively and do not apply another temperature factor
to the retained temperature minimum. The 64 nF 100 nF-part sensitivity assumption is intentionally
less evidentially strong and should not be promoted to an approved guaranteed
value without an impedance analyzer or vendor curve. The exact part identities
and ratings are supported by the [Samsung product page](https://product.samsungsem.com/mlcc/CL32B106KBJZW6E.do),
[Murata retained characterization](../components/sources/cout-bias-25-lowac.json),
and the [Murata temperature trace](../components/sources/cout-temperature-3v465-lowac.json).

## L2 normal versus fault stress

At nominal 5.6 uH, the 500 kHz ripple is 0.889–0.943 A p-p across the VIN
range. At tolerance minimum 4.48 uH and TI's 450 kHz minimum it is
1.237–1.310 A p-p, giving 1.118–1.155 A peak at 0.5 A and **1.618–1.655 A
peak at 1 A** at 3.3 V output. At the permitted 3.465 V output maximum the
same 450 kHz/L-minimum calculation gives 1.639–1.679 A peak at 1 A. Thus 1.60
A is only a nominal-frequency screen; it is not a full tolerance corner. The
current is far below
Bourns' 23 A Isat (20% drop, 25 °C) and 12.5 A Irms (40 °C rise, 25 °C
ambient), but those ratings do not establish 105 °C hotspot behavior.

Using copper's approximately 0.393%/°C temperature coefficient as a model,
10 mOhm at 25 °C becomes about 13.1 mOhm at 105 °C. Copper loss is therefore
about 3.3 mW at 0.5 A, 13.1 mW at 1 A, and 0.92 W at 8.35 A, before core loss
and switching ripple. Core loss, thermal spreading, airflow, pulse duration,
and the actual hot L(I,T) curve remain unobservable from the retained rating.
Bourns' official sheet reports the 23 A / 20%-drop point and the L-vs-I chart,
but does not turn it into a combined 105 °C guarantee: [Bourns SRP1265A
datasheet](https://www.bourns.com/docs/product-datasheets/srp1265a.pdf).

The 8.35 A test remains visible while parent review decides its milestone:
inject controlled DC bias at a controlled 105 °C hotspot and record
inductance, temperature rise, and recovery. The buck's
cycle-by-cycle peak/valley current limit and hiccup short-circuit protection
make sustained 8.35 A a fault waveform, not a regulated operating point.

## What remains unobservable from retained evidence

1. Measure VIN-pin ripple with the specified probe method at all six VIN/load
   points and record source impedance or upstream ripple separately; an RLC
   time-domain model may supplement the measurement.
2. Measure assembled C9/C11/C12 impedance or obtain vendor curves and validate
   the sensitivity assumptions on representative parts across bias and
   temperature; do not call the model a guarantee.
3. Measure L2 hotspot and normal current waveforms at 0.5 A continuous and 1 A
   / 10 ms pulse. Perform the 8.35 A test in a standalone fixture only.
