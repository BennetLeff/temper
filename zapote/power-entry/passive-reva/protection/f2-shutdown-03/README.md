# F2 detector, retained latch and gate shutdown experiment

This implements the four agreed steps as a separate32-component candidate:
faster voltage detection, a retained fault latch, direct gate-driver disable,
and executed F2-opening simulations. The circuit is built and checked in
simulation only. It is not an installed board change or qualified protection.

The source is [PowerEntryF2Shutdown](../../../../../elec/src/power_entry_f2_shutdown.ato).
Its signal path is:

```text
VD and VB tapped dividers → four TLV3202 comparisons → SN74HCS21 health
    → SN74HCS74 asynchronous clear / fresh ARM latch → UCC27624 EN
    → 10Ω gate resistor → MOSFET gate
```

The comparisons cover each bus's absolute overvoltage and mismatch in either
direction. A fault, permit loss or invalid-rails signal clears RUN. Health
return alone cannot set RUN; a fresh ARM edge is required. All interfaces are
HOT-referenced. The5V and15V supplies and a valid startup/rails qualification
signal are supplied interfaces to this experiment.

## Built and checked

- Atopile0.2.69 compiled32 components. `source-02` is authoritative.
- Six new Rust tests inspect the compiled physical-pin graph, source/export
  hashes, exact parts, divider values, comparator polarity, both logic gates,
  latch pins, unused inputs, reference returns and local bypass connections.
  Together with three prior sensing tests and the retained-board test, all10
  compiled tests pass (`compiled-tests.txt`).
- The independent TI SN74HCS74 model passes arm, fault clear, held-ARM recovery
  and fresh-edge recovery checks. TI's unchanged UCC27624 model also ran with
  a12nF authored load and10Ω gate resistance; EN0.8V→gate4V was0.360851µs.
  That is a gate-voltage observation, not a drain-current turn-off bound.
- The conditional static threshold screen was rerun with the prior authored
  error allowances. At VB410V, its relative-trip range is417.199–432.086V;
  these are assumed-corner results, not newly qualified comparator limits.
- Independent Luna circuit and simulation reviews challenge the implementation
  and measurements. See their reports and `review-resolution.md` for fixes
  and remaining limitations.

## What the simulation can establish

The complete behavioral path includes the divider RC, comparator response,
health logic, an edge-triggered retained latch, driver response, loaded gate,
MOS switch, healthy boost diode, inductor, local reservoir and opening F2.
The measured switch branch is separate from inductor current: the latter can
continue flowing through the diode after the switch stops conducting.

The provisional screen is2µs from the unfiltered bus-voltage trip condition
to sustained switch-current cessation, and500V maximum VD. Ordinary PWM off
time is not accepted as shutdown while later switch pulses remain possible.
Case names containing40/45/50 identify initial current, not a guaranteed
current at the later fault; the result table reports both actual event currents.

Final case results and their interpretation are recorded below and in
`simulation/traces/summary.csv`. A deliberately slowed driver is a negative
control and is expected to fail. Startup inhibition, rearm behavior and F2
shutdown timing are different tests and must not share an unexplained PASS.

## Final observed results

The canonical run contains19 scenarios:15 pass their stated model checks,
one deliberately slowed negative control fails, and three startup-voltage
cases are indeterminate for running-fault latency. Four extractor tests and
one manufacturer-log parser test pass in addition to the10 compiled tests.

| Case | Current at voltage threshold | Threshold→shutdown | Peak VD | Result |
|---|---:|---:|---:|---|
|40A initial /100µH |45.29A |0.734µs |446.23V |PASS |
|45A initial /180µH |48.16A |0.728µs |466.09V |PASS |
|50A initial /216µH |53.07A |0.726µs |482.83V |PASS |
|Gate pulse overlaps detection /1ns timestep |53.16A |0.976µs |483.97V |PASS |
|Doubled lumped gate charge |56.76A |0.960µs |490.76V |PASS |
|Deliberately slowed EN response |52.21A |4.889µs |477.61V |FAIL as intended |

The three initial runs shut down during a PWM off interval. Four additional
phase choices were therefore exercised. The1µs phase case has14.45V at the
gate and53.08A in the switch branch when Q clears, so it actually exercises
loaded gate turn-off. Its refined result is0.976µs. Halving the timestep
changes that delay by0.01427µs and peak VD by0.003762V; the original50A case
changes by0.002969µs and0.028501V. This is a finite phase/timestep screen,
not an exhaustive worst-case search or a guaranteed maximum.

The doubled-charge case changes the preceding switching trajectory and
threshold current as well as gate discharge. Its slightly shorter total delay
does not mean larger gate charge improves turn-off; its peak voltage rises.

Healthy switching, held-ARM recovery, fresh-edge rearm, permit loss/return
and rails-signal loss/return pass dedicated state assertions. These prove
pre-fault activity and retained shutdown in the observed windows; the fresh
rearm case also requires no current before its260µs ARM edge and activity
afterward. The independent TI latch fixture agrees with the state behavior.

**Three cases remain inconclusive:** reverse mismatch and the two startup
absolute-overvoltage cases do not establish a valid running-fault response.
The initial voltage difference equalizes through closed F2 and interacts with
startup/filter settling. Even the bank-side startup inhibit is not reported
as a zero-delay shutdown success. Both polarity connections are checked in
the compiled graph; isolated dynamic fault injection is still needed to
close this simulation coverage gap.

The ideal switch/diode model also produces implausible short current impulses
in running/rearm traces. Those values are retained and explicitly excluded
from physical stress or maximum-current claims. The peak-voltage and timing
results above apply only to this authored model.

Ngspice generated [voltage](simulation/voltage.svg) and
[gate-shutdown](simulation/shutdown.svg) SVG plots from the refined overlapping
gate-pulse case. Numerical extraction uses the complete traces, not the plots.

## Limits and next engineering decision

The direct latch-Q→ENA interface still needs design/verification for an
unpowered5V rail while aux15 remains present. A2.2k pulldown does not prove
the unspecified internal pullup/back-power behavior. Actual rail ramps,
supervisor behavior and input clamping are outside the fixed-supply model.

Actual fault-current maximum, L(I,T) bounds and complete MOSFET current-turnoff
maximum remain **null**. The exact ST model was unavailable in this run.
Typical gate charge and an ideal switch cannot close these quantities, nor
can a nominal comparator delay prove its response to the actual slow ramp.
F2 arcing, parasitics, saturation, component faults, temperature corners and
installed thermal/pulse capability remain outside this experiment.

The next decision is whether to retain this small circuit for the next
integration iteration after resolving the powered/unpowered EN interface and
improving the exact power-device model. Simulation results support choosing
what to develop; physical verification is still required before calling the
assembly protected.

See `source-model-binding.md`, `vendor/README.md`, `device-audit.md`, the
retained reviews, `claims.json` and `receipt.json` for the evidence boundary.
The retained54-component board, earlier F2 sensing experiment and timing
audit are unchanged; all32 previously recorded artifact hashes were verified.

## Reproduce

From the repository root:

```sh
cargo test --locked --offline --manifest-path zapote/Cargo.toml -p zapote-erc \
  --test f2_shutdown --test f2_sense --test passive_reva
sh zapote/power-entry/passive-reva/protection/f2-shutdown-03/simulation/run_cases.sh
cargo run --locked --offline --manifest-path zapote/Cargo.toml \
  -p zapote-harness --bin zapote-claims -- \
  zapote/power-entry/passive-reva/protection/f2-shutdown-03/claims.json
```

Run the separate manufacturer fixtures using `vendor/README.md`. Full trace
artifacts and the final receipt bind this run to the source, extractor and
models; a claims-check pass checks ledger consistency, not physical truth.
