# Corrective PFC loss experiment — 2026-09-17

This note supersedes the earlier Coss-equivalent loss number in
`DECISION.md`, `RESULTS.md` and `candidates.md`. It is a planning experiment;
it does not authorize a powered board or claim a complete loss budget.

## Device and source identity

The authored and native order code is `STW65N65DM2AG`; the package marking is
`65N65DM2`. The executable loss inputs now bind to retained
`sources/STW65N65DM2AG.pdf`, DocID028164 Rev 1: page 1 for identity, Table 6
for gate charge/resistance, page 7 Figure 12 for Eoss. The earlier Rev 2
curve claim was not bound to retained bytes and is superseded by
[EOSS-REV1-REBIND.md](EOSS-REV1-REBIND.md). Native board/source identities
remain AG; no board geometry changed in this model correction.

## Corrected output-capacitance term

The 456 pF `Coss eq.` value is defined by ST as a constant capacitance giving
the same charging time as Coss from 0 to 80% VDSS. It is therefore not an
energy-equivalent capacitance and must not be evaluated as
`0.5*C*Vbus^2*fsw`. The old calculation produced 4.468 W at the 389.615 V bus
and 129.107 kHz.

The Rust model now linearly interpolates these points digitized from the
typical Eoss curve in DocID028164 Rev 1 page 7 Figure 12 (joules):

```text
VDS (V):   0    50   100  150  200  250  300  350  400  450  500  550  600
Eoss (uJ): 0.0  2.8  4.1  5.3  7.0  9.0  11.5 14.3 17.5 21.0 24.8 29.0 33.5
```

At the experiment bus this gives `Eoss = 16.835 uJ` and
`P = Eoss*fsw = 2.174 W`, with an estimated ±0.6 uJ digitization/interpolation
uncertainty (±0.078 W at this frequency). This is a typical curve estimate,
not a maximum or a production guarantee. A measured Eon that already includes
the Coss discharge must not be added to this term.

## Reproducible switching model

The Rust event model in `zapote-erc::pfc_switching` now represents UCC28180
source/sink limits (1.5/2 A), the 10 ohm external plus 3.3 ohm intrinsic gate
network, a 6.2 V Miller plateau, VDS/current transition, 10 nH commutation loop
and Coss turn-on energy. It runs 54 line/bias/resistance/transfer-charge sensitivity cases.
At 120 Vrms, assumed 10 V bias, 10 nC transfer charge and 50 mΩ, the model reports 126.582 W overlap,
7.091 W conduction, 0.155 W gate charge and 2.174 W Eoss; peak VDS is
396.611 V at the phase-mean turn-off current; this is not a peak bound.
The split-stage quadrature agrees with independent triangle-area anchors. These
are conditional model outputs, not hardware validation.

Run details, model inputs, hashes and the complete JSON result are in
`PFC-SWITCHING-MODEL.md` and `evidence/correction-02/loss-report.json`.

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

The corrected sensitivity exceeds the prior heat allowance and does not
endorse the existing gate drive. It also cannot by itself select a replacement: the exact AG part is
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
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo test --manifest-path zapote/Cargo.toml --release --locked --offline -p zapote-erc pfc_losses
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo test --manifest-path zapote/Cargo.toml --release --locked --offline -p zapote-harness boost_switch
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo run --manifest-path zapote/Cargo.toml --release --locked --offline --bin zapote-pfc-loss -- zapote/power-entry/shunt-repair/candidate/source-manifest.json > /tmp/current-pfc-loss.json
```

The tests include an independent regression that rejects use of the
time-equivalent 456 pF formula by requiring the corrected Eoss result to be
below 2.7 W and materially below the old 4.468 W value.
