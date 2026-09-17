# Corrective PFC loss experiment — 2026-09-17

This note supersedes the earlier Coss-equivalent loss number in
`DECISION.md`, `RESULTS.md` and `candidates.md`. It is a planning experiment;
it does not authorize a powered board or claim a complete loss budget.

## Device and source identity

The authored and native order code is `STW65N65DM2AG`; the package marking is
`65N65DM2`. The exact selected
source is the official [STW65N65DM2AG DS11178 Rev 2, December 2025](https://www.st.com/resource/en/datasheet/stw65n65dm2ag.pdf),
page 1 (identity) and page 6, Figure 8 (Eoss curve). The retained local
`sources/STW65N65DM2AG.pdf` is an older DocID028164 Rev 1 copy and remains
hash-pinned for the other typical values; the revision difference is recorded
instead of being hidden. The native board/source artifacts were regenerated
together and bind the same current-board hash. The physical marking is retained
only as package identity.

## Corrected output-capacitance term

The 456 pF `Coss eq.` value is defined by ST as a constant capacitance giving
the same charging time as Coss from 0 to 80% VDSS. It is therefore not an
energy-equivalent capacitance and must not be evaluated as
`0.5*C*Vbus^2*fsw`. The old calculation produced 4.468 W at the 389.615 V bus
and 129.107 kHz.

The Rust model now linearly interpolates these points digitized from the
typical Eoss curve in DS11178 Rev 2 Figure 8 (joules):

```text
VDS (V):   0    50   100  150  200  250  300  350  400  450  500  550  600
Eoss (uJ): 0.0  2.1  4.1  5.5  6.9  8.8  11.1 15.0 19.5 24.0 28.6 33.3 37.8
```

At the experiment bus this gives `Eoss = 18.565 uJ` and
`P = Eoss*fsw = 2.397 W`, with an estimated ±0.6 uJ digitization/interpolation
uncertainty (±0.078 W at this frequency). This is a typical curve estimate,
not a maximum or a production guarantee. A measured Eon that already includes
the Coss discharge must not be added to this term.

## Reproducible switching model

The Rust event model in `zapote-erc::pfc_switching` now represents UCC28180
source/sink limits (1.5/2 A), the 10 ohm external plus 3.3 ohm intrinsic gate
network, a 6.2 V Miller plateau, VDS/current transition, 10 nH commutation loop
and Coss turn-on energy. It runs 18 reproducible line/bias/temperature cases.
At 120 Vrms, 10 V bias and 25 C, the model reports 43.943 W overlap,
11.261 W conduction, 0.155 W gate charge and 2.397 W Eoss; peak VDS is
390.822 V including the modeled loop overshoot. The 0.25 ns result is within
0.4% of the 1 ns refinement, with explicit per-event energy accounting. These
are typical, bounded model outputs, not hardware validation.

Run details, model inputs, hashes and the complete JSON result are in
`PFC-SWITCHING-MODEL.md` and `evidence/pfc-loss-simulation-2026-09-17.json`.

The decisive missing input is a double-pulse or equivalent switching capture
at roughly 390 V, the actual inductor current, the 10 ohm network, the chosen
UCC28180 bias and hot/cold device temperatures. The capture must state whether
Eon includes Coss discharge so the terms are partitioned once.

## Current GBJ assembly cooling decision

The applicable assembly is the current GBJ study, not the historical GBU
study: Wakefield 392-120AB and Sanyo 9RA1212E1001. The retained
`power-entry/shunt-repair/bridge-thermal-02/assessment.json` binds the current
board/native/manufacturing/waveform hashes and reports:

| case | whole-joint peak | hottest GBJ node | status against 110/125 °C screens |
| --- | ---: | ---: | --- |
| nominal-fine | 84.35 °C | 80.22 °C | conditional margin 25.65/44.78 K |
| weak-assembly | 117.82 °C | 95.95 °C | fails 110 °C local screen |
| fan-loss | 118.64 °C | 119.53 °C | fails 110 °C local screen; 5.47 K to 125 °C node target |

The GBJ README's 100 CFM catalog calculation (59.64 °C) is a conditional
reservoir calculation, not installed airflow evidence. The nominal and weak
contact paths, duct pressure/recirculation, fan fault transient and unresolved
pad/contact current split keep cooling applicability **INDETERMINATE**. No
GBU2510A/Wakefield 395-1AB margin is transferred to this GBJ assembly.

## Decision

The bounded model does not justify a MOSFET replacement: the exact AG part is
selected, but hot RDS(on), measured Eon/Eoff and commutation/protection costs
remain open. It does not justify changing the 10 ohm gate network yet; the
event model identifies gate timing as a high-value measurement, not a validated
optimum. The baseline still needs a qualified current GBJ
thermal/contact and installed-airflow path. Cooling work is therefore required
for baseline closure, while device and gate-drive changes remain measurement-
gated. The 62.9 mΩ active-bridge number remains a conduction-only screen and
is not an architecture decision.

The corrected nominal input requirement remains **1,796.416 W at 120 Vrms and
15 Arms**; it is not DC output power. At 108 Vrms the current model needs
16.658 A, so the 15 A ceiling reaches only 1,617.1 W.

## Reproduction and tests

From the isolated checkout, with the locked offline workspace:

```sh
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo test --locked --offline -p zapote-erc pfc_losses
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo test --locked --offline -p zapote-harness boost_switch
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo run --locked --offline --bin zapote-pfc-loss -- power-entry/shunt-repair/candidate/source-manifest.json > power-entry/loss-budget/evidence/pfc-loss-simulation-2026-09-17.json
```

The tests include an independent regression that rejects use of the
time-equivalent 456 pF formula by requiring the corrected Eoss result to be
below 2.7 W and materially below the old 4.468 W value.
