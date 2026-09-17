# Reproducible PFC switching model — 2026-09-17

The executable model is Rust zapote-erc::pfc_switching, reached through
zapote-pfc-loss. It is a deterministic hard-switched boost commutation
model, not an averaged loss spreadsheet and not a hardware qualification.
The retained STW65N65DM2AG PDF is the source for Qg=120 nC, Qgd=58 nC,
and the digitized typical Eoss(VDS) curve. The TI UCC28180D source supplies
the 1.5 A source and 2 A sink peak-current representation. The authored
network is 10 ohm external plus 3.3 ohm intrinsic gate resistance.

For each turn-on and turn-off event, the model charges Qgs = Qg-Qgd up to a
6.2 V assumed Miller plateau and integrates a 58 nC Miller interval with the
driver current limited by both the UCC28180 peak rating and the 13.3 ohm
gate path. Turn-on current ramps from zero to the CCM event current while
VDS falls from the 389.615 V bus to I·RDS(on); turn-off uses the reverse
current/voltage ramp. The 10 nH loop value is a named sensitivity and adds
L·di/dt to turn-off VDS peak. The C3D20065D diode is ideal for this scope
(zero reverse recovery); its reverse-recovery and capacitance terms remain
open. Eoss is added once on turn-on and is never added to measured overlap
energy. Qg·Vdrive·f is reported separately from the controller's loaded
15 V·7 mA ICC; those terms are not summed as independent controller
quiescent power.

The 18 scenarios cover 108/120/132 Vrms current moments, 9/10/11 V gate
bias, and 25/125 °C RDS(on) sensitivities. The 120 Vrms/10 V/25 °C case
produces 43.943 W integrated overlap, 2.397 W Eoss, 11.261 W conduction and
0.155 W gate charge (55.359 W for these switch terms). The corresponding
125 °C/100 mΩ case is retained in the raw JSON. These are typical/model
results and sensitivity points, not guaranteed bounds.

The fixed step is 0.25 ns. Each event records its step count and relative
energy-balance error; the Rust test reruns at 1 ns and 0.25 ns and requires
less than 1% switching-loss change. Reproduce the receipt with:

    CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo run --locked --offline \
      --bin zapote-pfc-loss -- \
      power-entry/shunt-repair/candidate/source-manifest.json \
      > power-entry/loss-budget/evidence/pfc-loss-simulation-2026-09-17.json

The raw receipt, retained source hashes and model inputs are
evidence/pfc-loss-simulation-2026-09-17.json and
pfc-switching-model-2026-09-17.json. A double-pulse capture at the actual
390 V bus, commutation current, gate network and hot/cold device temperatures
is still required before claiming production Eon/Eoff or hardware thermal
qualification. Startup, fault, EMI, ringing and installed cooling remain
outside this model.
