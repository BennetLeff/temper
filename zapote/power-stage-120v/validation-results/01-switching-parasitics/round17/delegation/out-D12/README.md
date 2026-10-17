# D12 — build proposals for F6 and F7

**Recommend the precision 49.9kΩ F7 resistor substitution as the first nominal-operation experiment; it changes no extracted copper, costs about $0.20 to rework both legs, and its estimated 396.636–488.003ns interval fits inside the sampled 391–498ns grid. It is not a guaranteed timing fix or an S4 remedy.** If S4 immunity is mandatory, retain F6 as the development direction, preferably the −2V class with fast discharge; the inexpensive bootstrap-compatible Zener network specified here does **not** reproduce D6's stiff +15/−2V or +15/−4V sources. It sacrifices positive gate drive, has no negative bias on the first pulse and has unqualified low-current Zener behavior. The preferred F6 development proposal is the independently supplied +15 V/negative-rail design in [ISOLATED-BIAS.md](ISOLATED-BIAS.md), approximately $119/$115 including supply replacement and hardware bias-ready isolation. The owner must decide whether nominal-only F7 is acceptable, or whether the broader F6 supply/layout change is justified. Neither proposal closes release qualification.

Scope: proposal only, based on `a5eddd2bec65d0dd026bdd47087947b0b22cbfd6`.
No schematic, board, firmware or netlist was changed. The supplied task asks
for a guaranteed minimum using D1's stack; **that guarantee is unavailable**.
This report carries the estimate with its missing specification intact.

## Comparison

The first table records the cheaper **screened passive alternatives**, whose positive-drive/startup mismatch prevents treating them as implementations of D6. For the separately powered F6 proposal that addresses those limitations, see [ISOLATED-BIAS.md](ISOLATED-BIAS.md).

USD material estimates for one complete board, accessed 2026-10-02; no labor,
shipping, tax or tooling. Source/price detail: [SOURCES.md](SOURCES.md),
[prices.csv](prices.csv), computed [evidence.json](evidence.json).

| | F6 −2V class | F6 −4V class | F7 recommended |
|---|---|---|---|
| Circuit | TI Fig.8-4 series bias network, 1nF Cgs, 1Ω+Schottky discharge branch | Same series bias network with 3.9V Zener and 1nF Cgs; retain single 3.9Ω Rg | R9/R17 →49.9kΩ ±0.1%,25ppm/°C |
| Gate levels, ideal settled 15V supply | About +13/−2V | About +11.1/−3.9V, **not exact −4V** | Existing unipolar gate drive |
| Added parts | Four each: Zener, blocking capacitor, Cgs, discharge diode, resistor; 20 total | Four each: Zener, blocking capacitor, Cgs; 12 total | No added placements; replace 2 resistors |
| BOM delta | +$8.60 | +$5.00 | New-build −$0.02 using observed small-quantity prices; rework purchase $0.20 |
| FEM | Rerun both legs after routing | Rerun both legs after routing | No rerun if footprints/routing/pads/stackup unchanged |
| Circuit simulations needed | Real bias startup, duty, parts/parasitics, reduced positive drive, hot corners | Same, plus 3.9V versus ideal 4V sensitivity | Actual gate timing and loss validation; no geometry re-extraction |
| Residual risk | Startup/burst bias collapse, Zener knee/temperature, diode/package parasitics | Same; lower positive gate overdrive, sourcing of blocking cap | S4 still fails; light-load ZVS/loss; minimum is an estimate |

D6's ideal −2V+fast-discharge+1nF and −4V+1nF cases pass its 32 decision
cases (including S4) at the original transient temperature. Those are
**simulation-only results for different drive sources**, not passes for the
parts below. See [D6](../out-D6/README.md). The 1.9V screen is provisional;
it must not be replaced by a typical model's threshold-minus-margin without
also preserving the minimum-based criterion.

| Independently powered F6 | −2 V variant | −4 V variant |
|---|---|---|
| Circuit | Four regulated isolated +15/−6 V modules, negative LDO, 1 nF, diode/1 Ω discharge | Same supplies/monitor, 1 nF, existing 3.9 Ω only |
| Gate targets | +15.026/−1.997 V | +15.026/−3.963 V |
| Material purchase estimate | About $119; 215 purchased parts including PS2 replacement | About $115; 207 purchased parts including PS2 replacement |
| Startup/duty | Independent bias before PWM; isolated rail-window hardware gates DIS; no bootstrap refresh duty | Same |
| FEM and layout | Both legs rerun; new PS2 footprint and isolation/thermal review | Same |
| Remaining evidence | Actual supply/monitor startup and hot transient qualification; selected resistor prices partly family estimates | Same, plus actual −3.963 V versus ideal −4 V sensitivity |

## Exact proposed connections against frozen/default.net

`evidence.py` imports D1's read-only S-expression parser and verifies the
actual memberships below. MOSFET pin 1 is gate, pin 3 is source. Part prefixes
`D12_*` are proposal aliases, not allocated design references.

| Channel | OUT net/pin | Existing Rg | Gate net | Source | Existing 10kΩ Rgs |
|---|---|---|---|---|---|
| Q2 | `leg_a-out_h`,U1.15 | R10 | `leg_a-gate_h` | `sw_a` | R11 |
| Q3 | `leg_a-out_l`,U1.10 | R12 | `leg_a-gate_l` | `leg_ret` | R13 |
| Q5 | `leg_b-out_h`,U2.15 | R18 | `leg_b-gate_h` | `sw_b` | R19 |
| Q6 | `leg_b-out_l`,U2.10 | R20 | `leg_b-gate_l` | `leg_ret` | R21 |

For each Q in the table, the **passive-option** F6 changes are:

1. Disconnect **only Rg pin 1** from OUT; connect it to new `D12_Q_shift`.
   Rg pin 2 remains on Gate. Retain the existing 3.9Ω 1206 part.
2. Add `D12_Q_Z`: cathode to OUT, anode to Shift. Use BZT52C2V0-7-F
   for the −2V class, BZT52C3V9-7-F for the −4V class.
3. Add `D12_Q_CZ` 10 µF in parallel with Z between OUT and Shift. This is a
   nonpolar blocking capacitor, **not** the 1nF gate capacitor.
4. Add `D12_Q_CGS` 1 nF directly between Gate and Source at the MOSFET.
   Keep existing Rgs and all existing drain-source capacitors unchanged.
5. For −2V only, add `D12_Q_DOFF` with **anode to Gate**, cathode to new
   `D12_Q_discharge`; add `D12_Q_ROFF` 1 Ω between Discharge and Shift.
   This conducts gate discharge towards the driver. When forward conducting,
   the external incremental resistance is 1Ω∥3.9Ω≈0.796Ω, plus the model's
   0.55Ω sink resistance; diode Vf and parasitics still matter.

In this passive F6 option, no existing part is removed. U1/U2 VSSA remain `sw_a`/`sw_b`; both
VSSB remain `leg_ret`; VDDB remains `v15_ls`; VDDA remain the bootstrap
rails `leg_a-boot`/`leg_b-boot`. D1/D2, existing bootstrap/bypass capacitors
and the 15V source are retained. No new isolated power supply is in this BOM.
Do not move the UCC VSS pins below the sources for this Fig.8-4 circuit.

For F7, remove the fitted RC0603FR-0739KL at **R9 and R17** and fit
RT0603BRD0749K9L in the same 0603 footprints. R9.1/U1.6 remain
`leg_a.driver-dt`, R17.1/U2.6 remain `leg_b.driver-dt`; both resistor pin 2
remain `selv_gnd`. No other pin, net or copper changes are proposed.

## Why the passive F6 circuit is conditional

TI SLUSE89C §8.2.2.9, Fig.8-4 p.36 supports a Zener/capacitor gate-path
network on the existing bootstrap supplies. Figs.8-2/8-3 pp.34–35 instead
split isolated bias or use separate positive/negative rails. They can retain
+15V while adding negative bias, with 17/19V total driver span below the 25V
recommended maximum, but require independently referenced supplies and
startup sequencing for the two high-side domains and the common low-side
domain. They are **not** obtained by reconnecting the existing bootstrap
return. The passive option quantifies Fig.8-4 as the smallest change. The separate
supply design is now specified and costed in ISOLATED-BIAS.md; neither
option is represented as hardware-qualified.

The selected topology retains approximately 15V across each driver supply,
within the 9.2–25V recommended B-variant range when the original supply is
healthy (TI pp.5,38). It shifts the gate waveform rather than increasing
supply span. A 1 V bootstrap-diode-drop scenario reduces the high-side on
levels further to about 12/10.1V. These are sizing scenarios, not guaranteed
PS2/diode output limits. Raising PS2 to 17/19V is **not** proposed: it would
change every load on that rail and requires a separate supply review.

[The analytical worksheet](bias_network.json) deliberately exposes the
limitations instead of treating the Zener as an ideal negative source:

- At 50% duty with 10kΩ Rgs, on-state resistor current is only 1.30/1.11mA;
  the net average current available to maintain the 2/3.9V bias is about
  0.55/0.36mA. The Zeners are specified at 5mA, and have 600Ω maximum knee
  impedance at 1mA. Their nameplate voltage is therefore **not established
  in this circuit**. No −2 V or −3.9V minimum bias is guaranteed.
- In an ideal constant-clamp, cycle-average model, `bias ≤ duty×15V`;
  sustaining 2/3.9V requires duty above 13.33/26%. These are necessary
  model conditions, not validated operating limits. Near 50% phase-shift
  operation is compatible in principle; pulse suppression and burst modes
  need separate validation. TI itself cautions about duty dependence.
- For 10µF and 10kΩ the nominal decay time constant is 100ms. A simplified
  startup estimate is 31.0/73.4ms to reach the target at 50% duty. Before the
  first pulse, bias is 0V. After 100ms disabled, an initially charged bias
  falls to about −0.736/−1.435V in that model. These estimates ignore
  asymmetric gate-charge injection and the real knee, so they are warnings
  to simulate and measure, **not firmware delay prescriptions**.
- A large blocking capacitor reduces edge ripple: using the datasheet's
 234nC typical Qg plus the added 15nC gives 24.9mV at 10µF. A deliberately
  assumed 400nC gate-charge scenario and 5µF effective capacitance gives 83mV.
  Neither assumed Qg nor effective capacitance is a worst-case bound.
  X7R bias/temperature/aging, capacitor ESR/ESL and placement must enter
  the final circuit model; decreasing CZ improves acquisition but worsens
  ripple. 10 µF is a prototype sizing choice, not an optimum.

**Bootstrap/startup acceptance is not demonstrated by this proposal.**
The high-side supply must be refreshed by low-side conduction/freewheeling;
100% high-side duty is prohibited with the retained bootstrap (TI p.36).
A conditional worksheet starting at 13V with 5µF effective CBOOT, 415nC
per switch and 4.4mA driver-current sizing gives 83mV droop per turn-on,
about 4.22ms to 9.2V with no refresh, and 635nC/cycle replenishment at 20kHz
(0.635A average if confined to 1µs). The 4.4mA value is TI's 500kHz table
condition, not a universal current bound. Bootstrap charging impedance,
supply sag, diode recovery and available low-side dwell must be modeled
before accepting those times. UVLO observes **driver supply**, not the bias
capacitor or positive gate plateau: B-variant rising threshold 7.7–8.9V and
falling 7.2–8.4V (TI p.9), with up to 10µs VDD startup delay (p.19). Healthy
UVLO status cannot certify negative bias. Keep both legs inhibited until
supplies/bootstrap are ready, then use a validated low-energy bias-acquisition
sequence; if S4-like switching can occur on restart, this topology is not
an established solution and independently powered bias is the next design.

## F7 timing calculation

[dt_resistor.py](dt_resistor.py) and [output](dt_resistor.json) use exactly
D1's multiplicative initial-tolerance/TCR method at resistor temperatures
−40,25,150°C. TI's timing limits already cover full driver temperature.
`DTnom = 8.6R + 13`; min/max estimates use the straight lines through
TI's 20 kΩ and 50kΩ specified rows. Where Rmax exceeds 50kΩ, this is explicitly
**extrapolation**; elsewhere it is interpolation. Neither creates a guarantee.

| Resistor | Tolerance/TCR | Estimated min ns | Nominal fit ns | Estimated max ns |
|---|---|---:|---:|---:|
| Existing 39kΩ | ±1%,100ppm/°C |307.185|348.400|391.220|
|49.9kΩ with D1's original stack | ±1%,100ppm/°C |389.592|442.140|496.741|
|51kΩ with D1's original stack | ±1%,100ppm/°C |397.909|451.600|507.390|
| **Selected 49.9kΩ RT precision part** | **±0.1%,25ppm/°C** |**396.636**|**442.140**|**488.003**|

A standard 49.9kΩ replacement fails even the requested estimated 391ns
minimum. 51 kΩ meets that estimate but goes beyond the 498ns simulated end
point. The precision 49.9kΩ option improves the resistance stack and lies
inside the grid span; interpolation between sampled times still requires
validation. The guaranteed TI 399 ns minimum at **exactly 50kΩ** is not a
blanket guarantee at 49.9kΩ with tolerance, supply/loading differences or
at the MOSFET threshold. Obtain TI limits at the proposed network and
qualify assembled firmware-to-gate timing before claiming minimum 391ns.
D1's range, D5's input/driver timing and actual gate turn-off remain distinct.

## Parts, ratings and procurement

The source IDs below link to document/page details in [SOURCES.md](SOURCES.md).
Local passive temperature must meet its own rating even when MOSFET Tj is 150°C.

| Part / role | Relevant published ratings | Package; source |
|---|---|---|
| BZT52C2V0-7-F,2V Zener |1.91–2.09V at 5mA; ZZT≤100Ω at 5mA, ZZK≤600Ω at 1mA; tempco −3.5…0mV/°C at 5mA | SOD123; Z p.2 |
| BZT52C3V9-7-F,4V-class Zener |3.7–4.1V at 5mA; ZZT≤90Ω, same 600Ω knee and tempco | SOD123; Z p.2 |
| Both Zeners |370mW at ambient 25°C on specified board,500mW at lead 75°C; derate; −65…150°C; forward≤0.9V at 10mA | Z pp.1–2; do not treat 500mW as hot ambient allowance |
| PMEG6030EP,115, discharge |60V;3A average under datasheet duty/thermal conditions; VF≤0.53V at 3A,25°C; Cd typically 360pF at 1V and 120pF at 10V; Tj≤150°C | CFP5/SOD128; D pp.1–4 |
| RC1206FR-071RL, discharge |1Ω ±1%, ±200ppm/°C,0.25W at 70°C,−55…155°C |1206; ROFF p.1; repetitive gate pulses still need pulse-load assessment |
| C0603C102J5GACTU, added Cgs |1nF ±5%,50V, C0G ±30ppm/°C,−55…125°C |0603; CG p.1/exact part row |
| UMK325AB7106KM-T, CZ |10µF ±10%,50V,X7R ±15%,−55…125°C; DC-bias loss is additional |1210; CZ manufacturer Specifications |
| RT0603BRD0749K9L, R9/R17 |49.9kΩ ±0.1%,±25ppm/°C,0.1W at 70°C,75V max continuous,−55…155°C |0603; DT p.1 |

The Schottky choice avoids relying on a slow rectifier's minority-carrier
recovery, but its datasheet provides **no guaranteed trr/Qrr**; it is not
an ideal diode, and its substantial capacitance must be modeled. Its 50A
nonrepetitive surge rating is not a repetitive gate-pulse rating. UCC21550's
6A sink capability and the selected resistor can expose pulses above the
3A average rating; qualify peak current, pulse heating and the real Vf
curve. The 3.9Ω path stays in parallel, so ideal parallel resistance alone
cannot predict discharge speed.

All quoted parts were orderable at the retrieved distributor pages. The
PMEG6030EP,115 page showed only 9 in stock, enough for one board's 4; this
is not a production availability claim. CZ is manufacturer **Non-preferred**
and distributor **not recommended for new design** despite stocked inventory;
use only for the priced prototype or select/requalify a supported equivalent
before production. Reusing the frozen Murata 10µF part is not assumed: its
retrieved DigiKey listing could not accept backorders. No purchase was made.

## Layout, extraction and losses

`evidence.py` actually calls `leg_region_diff.py`'s parser, region selection
and comparator on a temporary **value-only** R9/R17 fixture. Both legs report
UNCHANGED, and stackup is identical. This tests the intended F7 ECO condition,
not an edited design. Component value properties are absent from the copper
comparison; a changed footprint, pad, location, net, via, fill or stackup
would invalidate it. After any real ECO, compare the saved boards again.

F6 inserts parts in all four gate paths and adds Cgs at the MOSFETs: both
extraction regions change. Crop margins overlap, so even a one-leg edit can
require both reruns if it lands in the overlap. Existing gate parts inside
each actual crop are listed in `evidence.json`. Rerun circuit transients
with the new components regardless of FEM; FEM does not model Zener knee,
UVLO or capacitor startup.

Planning allowances, not measured geometry: per gate allow 12–25mm extra
track for −2V (bias network + discharge branch) and 6–12mm for −4V (bias
network), at 0.5mm width. Across the bridge this is 24–50mm² or 12–24mm²
of added **trace** copper, excluding lands/planes. These allowances are
explicit inputs in `evidence.json`; no inductance claim is derived from
them. Keep the new Cgs return at the same local MOSFET source, minimize
OUT/Shift/Gate loop area, and preserve driver isolation spacing. Placement
may prove the allowances optimistic and force a larger crop.

Adding 1nF costs 15nC and 0.225µJ per gate cycle at a 15 V swing, or 17/19nC
and 0.289/0.361µJ for D6's ideal 17/19V swings. At the illustrative 40kHz
rate this is 0.036/0.04624/0.05776W across four gates. This is capacitor
charging loss only, distributed among driver, resistors and diode. The
worksheet includes a resistance-divider estimate for the single 3.9Ω path's driver share (not the fast-discharge branch);
real driver resistance, gate charge and temperature prevent turning that
into a driver-temperature prediction. Faster discharge can increase driver
sink dissipation, ringing and EMI; lower positive voltage can increase
MOSFET conduction loss. F6's costs are not just its BOM.

The committed long-DT grid has 408 cases and 6 aborts. Its complete nominal
S1 points preserve ZVS and pass the hot screen at 391/443/498ns, whereas
S4 fails: see the per-case/per-time recount in `evidence.json`. Light-load
points require their own ZVS/loss decision. [D15's completed 240-case map](https://github.com/BennetLeff/temper/pull/1637)
(`out-D15/TABLES.md`, companion report) finds **no sampled ZVS point lost**
from 348 to 443 ns: both have 24/48 ZVS decisions, at 20/30/37 A;
2/5/10 A remain hard. At 498 ns the 10 A cases also pass (32/48).
Its 37 A switching subtotal rises about 0.09234–0.11029 W/switch at the
assumed 36 kHz; the refined 198 V, 1.06 nH value is 0.111231 W/switch.
At 2/5 A the subtotal falls about 1.16–2.97 W/switch despite remaining hard.
Thus the brief's “costs light-load ZVS” is not supported by the sampled map.
These are representative switching-cycle proxies, not appliance efficiency
or thermal loss. The diode diagnostic overlaps the subtotal and must not
be added again. D15 is a parallel deliverable, not part of the frozen base. The completed
[D13 hot-switching study](https://github.com/BennetLeff/temper/pull/1636)
finds that all 56 ideal F6 −2 V cases at 150 °C abort; cooler passes do not
qualify hot F6. Every completed F7 S4 case still fails the off-gate screens.
D14's solver/convergence qualification remains an independent dependency.

## Reproduce and acceptance status

From the repository root (Python 3.12 plus Shapely; no Rust/native build):

```sh
D12=zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D12
/Users/bennet/Miniforge3/bin/python3 "$D12/dt_resistor.py"
/Users/bennet/Miniforge3/bin/python3 "$D12/bias_network.py"
/Users/bennet/Miniforge3/bin/python3 "$D12/evidence.py"
/Users/bennet/Miniforge3/bin/python3 "$D12/isolated_bias.py"
```

This regenerates the four JSON outputs from the committed scripts/prices
and frozen source data. `verification.txt` records the executed checks.
Scripts are evidence worksheets authorized by the brief, not engineering
rules added to the Rust validator. No ngspice was run here; existing grid
results are recounted with input hashes.

Completed: exact net edits, orderable prototype BOM and costs, timing
estimates, supply/startup/duty analysis, source register, geometric rerun
classification and rerunnable calculations. **Not established:** guaranteed
minimum dead time; negative-bias magnitude/startup efficacy for the selected
parts; actual post-layout copper and switch losses. These are technical
findings, not hidden passes. Both specified F6 circuits remain proposals. Independent supplies remove
the passive network’s known positive-drive and first-pulse limitations, but
startup/interlock simulations and hardware evidence remain required before
calling either simulated ideal remedy build-equivalent.
