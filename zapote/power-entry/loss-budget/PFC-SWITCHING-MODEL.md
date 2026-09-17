# PFC switching sensitivity — corrected 2026-09-17

The executable Rust model `zapote-erc::pfc_switching` now uses separate
current-transfer and Miller voltage-transition stages. This supersedes the
waveform and conclusions in `evidence/pfc-loss-simulation-2026-09-17.json`
and `pfc-switching-model-2026-09-17.json`; those files are preserved as history.
The current output is [correction-02/loss-report.json](evidence/correction-02/loss-report.json).

## Physical and numerical contract

[TI SLUA618A, figures 3–5](https://www.ti.com/lit/ml/slua618a/slua618a.pdf)
describes clamped-inductive switching: on turn-on, current rises at the bus
voltage, then voltage falls at approximately fixed inductor current. Turn-off
reverses that order. Our linear approximation has energy
`Vbus * I * (t_current + t_Miller) / 2` for each event. It omits diode
capacitance, ringing, reverse-commutation detail and nonlinear gate dynamics.
It is a sensitivity estimate, not a solved circuit or a physical upper bound.

Inputs and limitations:

- Separate phase-mean on/off currents come from the CCM waveform. Averaging
  these currents is valid for this linear energy approximation, whose charge
  and gate current are held constant across phase; it is not a nonlinear
  device model. Conduction uses the MOSFET's duty-weighted RMS current.
- Current-transfer charge is explicitly **5/10/20 nC assumed**, never `Qg-Qgd`
  or total Qgs. These points have no claim to bound the physical device.
- Qg=120 nC, Qgd=58 nC and intrinsic Rg=3.3 Ω come from the retained Rev 1
  datasheet. See [the exact Eoss source correction](EOSS-REV1-REBIND.md).
- The 10 Ω external gate resistance is authored. Gate bias 9/10/11 V and
  plateau 6.2 V are assumptions; the circuit's 15 V supply does not establish
  the actual gate waveform. Driver currents use the resistive plateau
  estimate capped by UCC28180 1.5 A source / 2 A sink ratings. Peak ratings
  are not the controller's output I–V curve.
- The nominal 50 mΩ and hot 100 mΩ cases are resistance sensitivities.
  Temperature labels do not imply an electrothermal solution.
- `L*di/dt` uses an assumed 10 nH and the **current-transfer** duration.
  Reported voltage uses the phase-mean event current; it cannot bound the
  line-cycle peak or qualify drain-voltage rating.
- Eoss is added once. Gate `Qg*V*f` is separate from die loss, and is never
  added to the controller's loaded ICC as if that were quiescent current.

54 points cover three line voltages at fixed 15 Arms (different powers), three
assumed gate biases, two resistances and three transfer charges. The nominal
120 Vrms / 10 V / 50 mΩ / 10 nC point reports:

| Term | W |
|---|---:|
| Overlap only | 126.582 |
| Eoss | 2.174 |
| Switching subtotal | 128.756 |
| Duty-weighted conduction | 7.091 |
| Partial modeled MOSFET loss | 135.847 |
| Gate network, separate | 0.155 |
| MOSFET plus gate subtotal | 136.002 |

This exceeds the old 105 W whole-electronics allowance before including many
other components. **It invalidates using the old low-loss result to endorse
the present gate drive. It does not establish actual temperature or require a
part change by itself.** Retain AG + 10 Ω as the experiment baseline only;
resolve actual gate voltage/drive strength, charge at operating current and
switching waveforms before claiming it is an acceptable production choice.
GBJ installed-cooling qualification remains independently necessary.

## Regression and evidence

The new Miller-triangle regression failed on the original model: about
198 µJ versus a 593 µJ Miller-only reference. The original waveform ramped
current and voltage simultaneously and omitted the physical current-transfer
stage. Its convergence test only reproduced that mistaken waveform.

Independent test anchors now include 400 V, 10 A, 20 ns current transfer and
30 ns Miller: **100 µJ per event**, **20 W per pair at 100 kHz**. Conduction
15² × 0.05 × 0.5 = **5.625 W**. Tests cover asymmetric event currents, driver
limits, zero current, Eoss once, stage ordering, timestep refinement and
invalid/unbounded inputs. The adapter checks the actual source-derived RMS
and event moments. Numerical triangle agreement is called **quadrature error**;
it is not conservation of energy in a modeled power circuit.

From the repository root:

```sh
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo test --manifest-path zapote/Cargo.toml --release --locked --offline -p zapote-erc pfc_switching
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo run --manifest-path zapote/Cargo.toml --release --locked --offline --bin zapote-pfc-loss -- zapote/power-entry/shunt-repair/candidate/source-manifest.json > /tmp/current-pfc-loss.json
```

The report exits **2 / INDETERMINATE** while loss and cooling coverage are
incomplete. Full-loss and cooling-margin fields remain null. Hardware
waveforms, diode/inductor/capacitor losses, startup/fault operation and
installed cooling remain unqualified.
