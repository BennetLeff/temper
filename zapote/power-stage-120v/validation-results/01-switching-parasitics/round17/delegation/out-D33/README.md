# D-33 — revised HOT-side bias: source freeze held

**The revised transformer path is not qualified for source freeze: sizing is
recorded, but the loaded-rail F6 campaign remains partly indeterminate.**
The circuit source, audit, frozen exports and board are unchanged. This is a
verification draft, not the requested completed native-21 source delivery.

The branch starts at `3b0abe9776c6fac81577d2617ef857497cbed781`, including
DECISIONS.md's 2026-10-06 **F6 bias architecture REVISED**. It supersedes both
the RECOM proposal and the SELV-fed proposal. No gate or protection load is
allocated to PS1/SELV here. The user's ordering constraint is preserved:
sizing and a passing rail-model rerun must precede circuit-source work.

## Candidate and sizing

Run `python3 zapote/power-stage-120v/native-21/bias_sizing.py` from the checkout.
Its output is [bias-sizing.json](bias-sizing.json).

The candidate is TCO_L → IRM-20-24, a direct low-side regulated 17 V span,
and one SN6507 driving two WE 750320775 transformers. Each floating secondary
needs a regulated 17 V span. A shunt fixes each source midpoint approximately
2 V above its negative terminal, yielding approximately +15/−2 V at the gate
driver. The low-side supply's negative terminal is thus at approximately
−2 V relative to `leg_ret`; it must not also be hard-tied to `leg_ret`.
HOT5 would use a TPS709-class LDO returning at R5.2, and its TPS3700 monitor
must retain an independent HOT-side supply. These are topology requirements,
not implemented connections.

The Qg reference is **234 nC typical at 10 V**, not a maximum at 15 V.
The calculation separately labels **400 nC** as an engineering allowance;
adding the 1 nF Cgs over a 17 V swing gives **417 nC**. Four-gate power is
0.936 W at 33 kHz and 2.268 W at 80 kHz. Including the stated driver, monitor,
bleed and HOT-load allocations, and an **assumed 70%** transformer conversion
efficiency, the raw-supply allocation is **3.514–5.575 W**. Efficiency has
not been measured or bounded. The 21.6 W supply rating provides allocation
headroom, but its temperature derating and the final netlist load still need
checking. The low-side span-regulator heat allocation is 0.634 W at 80 kHz;
the two high-side span regulators together account for 0.272 W.

The transformer has **3 pF typical** Cww, 500 Vrms reinforced working
insulation up to 700 kHz, 1.2:1 primary/secondary ratio, and a 60 Vµs
half-primary rating. These are distinct from its insulation test voltage.
The 21 kΩ SN6507 clock setting gives 523 kHz typical. Applying TI's −15%
frequency estimate gives 27.781 Vµs at the allocated maximum supply voltage.
The linear-core estimate gives 0.370 A total magnetizing peak plus 0.075 A
reflected load for two cores. This does **not** include recharge peaks,
startup flux, core loss or temperature-dependent winding resistance and
does not establish compliance with the driver's 0.5 A operating limit.
The 3 pF figure is not a maximum; the earlier 25 pF campaign is a separate
scenario, not a guaranteed bound for this part.

## Reservoir and regulator

Charge-only droop is 0.190 V with 2.2 µF effective, 0.0417 V with 10 µF,
and 0.0190 V with 22 µF. This calculation alone misses the edge inductance.
All capacitances in these models are **effective**, not nameplate values.
No capacitor MPN or layout has yet been qualified to deliver the model values.

The TLVH431 candidate uses a 6.12 kΩ/10 kΩ divider (1.99888 V nominal),
4.99 kΩ bleed and a local reservoir plus 100 nF. The standalone pulse test
uses the complete TI model with its TABLE functions translated algebraically
for ngspice. Paired 4 A pulses integrate to 417 nC each. At 80 kHz, the 10 µF,
20 mΩ, 0.5 nH bulk plus 100 nF, 50 mΩ, 0.1 nH circuit reaches
−1.765760 V and −2.239297 V. Increasing to 22 µF barely changes those edge
peaks: ESL matters. The active-region loop estimate gives phase margins of
4.27°, 9.45° and 14.06° for 2.2, 10 and 22 µF respectively. These are nominal
model calculations, not stability guarantees over component tolerance and
temperature. See [shunt-stability.json](shunt-stability.json) and
[shunt_stability.py](shunt_stability.py).

In a completed F6 diagnostic (leg A, 27°C, 170 V, −20 A, DIR=0, 391 ns,
film ESL 1.06 nH), changing only reservoir ESL from 0.5 to 0.25 to 0.125 nH
reduces the least-negative low-side excursion from about −1.442 V to
−1.649 V to −1.748 V. The latter two are **layout scenarios**, not measured
parasitics. The full grid uses 0.125 nH and 3 pF typical Cww; it cannot turn
that assumption into a component or board qualification.

## F6 method and limits

[rail_campaign.py](rail_campaign.py) reuses `d2/f6_legs.py`'s job construction,
PMEG6030EP model and switching verdicts. Both legs use the native-19 matrices,
with **legB-h0-corr-n19.matrix.txt**, at 27/100/150°C. The full grid has
288 decision cases and 216 S5 burst-start cases. The physical discharge
resistor is 1 Ω while the existing 3.9 Ω remains; the old deck's 1.3448 Ω
value was an effective-parallel-resistance choice. The 1 nF Cgs remains.

The new driver current returns to the actual positive/negative rail nodes.
Returning that current to the MOSFET source would leave the reservoir
unloaded and produce a false pass. The model includes negative-rail C,
ESR, ESL and shunt dynamics. It uses a **17 V Thevenin upstream regulator
(1 Ω and 47 µF)**, not a switched SN6507/transformer/rectifier/LDO model.
It therefore does **not** yet satisfy full real-supply qualification.
Shared low-side impedance, the second bridge leg and its transformer,
actual monitor loading, cold bias startup, TCO loss and component corners
also remain outside this deck.

Both full-grid solver runs are complete:

| Solver | Attempted | Completed and candidate-pass | Indeterminate |
| --- | ---: | ---: | ---: |
| Default Sparse | 504 | 299 | 205 |
| KLU | 504 | 171 | 333 |

**181 cases remain indeterminate in both solvers.** Of the 147 cases completed
by both, no candidate verdict differs; maximum differences are 1.0323 mV in
off-gate peak, 0.3696 V in die VDS peak and 0.184 mV in partner-window rail
peak. This agreement covers only that intersection. Default-solver completed
cases reach at most 1.020663 V off-gate, 492.0922 V die VDS, and −1.788605 V
on the least-negative partner-window rail. These extrema exclude aborted
cases and are not whole-envelope bounds. The 48 retained high-iteration
attempts contain 29 completed cases and 19 indeterminate cases.

See [campaign-comparison.json](campaign-comparison.json), the
[per-leg/temperature/case table](campaign-table.md), both campaign folders,
and [long-iteration-checks.json](long-iteration-checks.json). Generate the
comparison with `python3 .../out-D33/summarize.py`. The separate
[diagnostic records](diagnostics/records.json) retain the ESR/ESL and solver
experiments, including failures, with portable decks and hashes.

The complete TI shunt macro aborts during initialization in the mixed F6
deck. The campaign substitutes its two-pole active-region equations in a
local voltage frame, with a direct transconductance output. It rejects a
case unless **both control states remain strictly between 0 and 80 mV**.
The rail check requires both rails to remain below −1.6 V from the partner's
command through the following 0.75 µs, as well as at the command itself.
The outgoing turn-off excursion is recorded separately. A pass also needs
every canonical hot-screen, VDS, VGS, model-threshold and S1 ZVS condition.

`gmin=1e-7` is a numerical experiment, not a qualified universal fix.
Changing it to `2e-7` gave close results on one completed diagnostic, but
other cases still abort. The full screening run uses `itl4=1000`; selected
matching cases also ran with `itl4=100000`. A lower iteration count never
converts an abort into an electrical failure or a pass. Initializing with a
bus ramp, changing integration method/tolerances, adding a large shunt
resistance and reformulating the regulator port did not remove the general
convergence problem. All indeterminate cases stay visible.

S5 here means the first **bridge** edge with bias already energized. It is
not proof that the bias supply starts correctly or that the mandatory rail
monitor releases DIS correctly.

## Source hold and fallback

The next source gate requires a convergent, sensitivity-qualified full F6
grid with the actual supply impedance and realistic capacitor/ESL corners;
then regulator startup/thermal checks and a fail-safe rail-window monitor.
Only then should the bootstrap removal, HOT5 change, new parts, structural
mutation tests, atopile exports and native-21 ECO be implemented. The
existing R34/R8/R16/R9/R17 values remain untouched.

The brief's fallback is **bootstrap high sides with regulated split rails
and a low-side pre-charge before every burst**. It is not implemented or
validated here, and these numerical aborts do not establish that the
transformer hardware is infeasible. The fallback needs an explicit startup
sequence: if the mandatory all-rails monitor holds shared DIS active while
an empty bootstrap awaits a low-side pulse, the pulse cannot occur. That
interlock must be resolved in the fallback design; silently bypassing the
monitor or drawing gate power from PS1 would violate the brief.

## Reproduction

Use ngspice 45.2 and Python 3.12 with NumPy. Run from the checkout root:

```sh
zsh zapote/power-stage-120v/validation-plan/sim-kit/models/fetch_models.sh
python3 zapote/power-stage-120v/validation-plan/sim-kit/smoke_test.py
python3 zapote/power-stage-120v/native-21/bias_sizing.py
python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D33/shunt_stability.py
python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D33/rail_campaign.py --workers 4 --itl4 1000 --tag screen-3p-0p125n
python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D33/run_klu.py --workers 6 --itl4 1000 --tag klu-3p-0p125n
python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D33/summarize.py
python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D33/replay_diagnostics.py solver-direct
```

The TI archive is fetched and SHA-256 checked by the script. Licensed model
files and raw working directories are ignored; no vendor library is committed.
The standard model smoke test passes. Import-boundary and derived-artifact
checks pass; their logs are committed. Review was performed in the main
session, not by an independent reviewer. Atopile and new structural audit
tests were not run for this revision because the source gate is still held.

## Manufacturer references

- Infineon IPW65R018CFD7, Rev. 2.0, p.5 Table 6, Qg conditions; repository
  `validation-results/03-loss-thermal-budget/round3/sources/ipw65r018cfd7.pdf`.
- [Mean Well IRM-20 specification](https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF),
  2025-11-21, specification table and mechanical drawing: IRM-20-24 ratings,
  tolerance, ripple and 52.4 × 27.2 × 24 mm envelope.
- [WE 750320775](https://www.we-online.com/components/products/datasheet/750320775.pdf),
  revision 001.002, 2026-07-29, pp.1–2: winding data, Cww and working insulation.
- [TI SN6507](https://www.ti.com/lit/ds/symlink/sn6507.pdf), SLLSFM0A,
  June 2022, §§6.3/6.5, Table 8-1 and §9.2.2.5: current, clock and Vt sizing.
- [TI TLVH431](https://www.ti.com/lit/ds/symlink/tlvh431.pdf), SLVS555N,
  June 2024, p.11 stability curves and stability discussion; the plotted
  1.25/2.5/5 V examples do not guarantee this 2 V circuit.
- [TI SLVM672 model](https://www.ti.com/lit/zip/slvm672), model Final 1.00,
  2010-10-20, archive SHA-256
  `b658a78537ed2ba314fcfadf053686280c74e234f3e2ea6c2d846db245def7a6`.
- [Nexperia PMEG6030EP](https://assets.nexperia.com/documents/data-sheet/PMEG6030EP.pdf),
  pinning and manufacturer model, loaded by the existing hash-checked kit.
- [ngspice KLU selection](https://ngspice.sourceforge.io/applic.html),
  alternate matrix-solver option; selecting it does not qualify a circuit.
