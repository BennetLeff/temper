# Power-entry re-engineering candidate screen

This is the first executable pass at the reviewer's question: *is the 36-38 W
partial loss worth re-engineering the board for, and which architecture lever
actually moves it?* It compares five candidate architectures over the same five
operating cases and reports every term as either **computed from a source-bound
value** or **unresolved**. Nothing is zero-filled, no candidate is promoted, and
no total-loss or cooling-margin figure is produced.

Rust owns the screen (`packages/zapote-harness/src/pfc_candidates.rs`); it runs
inside the common unit runner, so its findings and rule coverage are retained
with the rest of the power-entry evidence rather than summarized by hand.

## The matrix

| Case | Conditions | Attached to |
| --- | --- | --- |
| 1 | 120 V RMS, full load, nominal cooling | 20 °C copper |
| 2 | 108 V RMS, full load | 20 °C copper |
| 3 | 132 V RMS, full load | 20 °C copper |
| 4 | Hot / degraded cooling | 120 V RMS at 100 °C copper |
| 5 | Startup, inrush, shutdown, fault | no CCM operating point |

Cases 1-3 hold the 15 A true-RMS input ceiling at every line voltage. Case 4 is
bound to copper temperature because that is the only cooling variable the
current CCM model can carry; it is not an ambient, airflow or junction
temperature. Case 5 has no CCM operating point at all, so it stays unresolved by
construction rather than being estimated.

## Computed results at the nominal case

| Candidate | Computed term | W |
| --- | --- | ---: |
| Keep bridge, improve thermal path | drop at 1.05 V (retained test point) | 28.304 |
| | drop at 0.85 / 1.30 V band | 22.912 / 35.042 |
| | drop sensitivity | 26.956 W/V |
| Larger / lower-drop passive bridge | drop at 1.05 V | 28.304 |
| | value of a 0.1 V improvement | 2.696 |
| Parallel passive bridges | drop, ideal split | 28.304 |
| | drop, all current in one bridge | 28.304 |
| | slope coefficient, ideal split / one bridge | 225 / 450 W/ohm |
| Active rectifier | conduction at 50 mOhm, 25 °C | 22.500 |
| | conduction at 100 mOhm, assumed hot | 45.000 |
| | reference passive bridge drop | 28.304 |
| Boost-stage optimization | MOSFET conduction, 50 / 100 mOhm | 7.091 / 14.183 |
| | MOSFET overlap, 50 ns edges | 33.898 |
| | gate drive, typical | 0.155 |
| | SiC capacitive, typical | 0.465 |

Three things follow, and they are the point of the screen.

**The line voltage barely moves the bridge term.** It computes 28.299 / 28.304 /
28.309 W at 132 / 120 / 108 V, because the model holds 15 A true RMS at every
line voltage and the drop term follows the rectified current mean, not the
voltage. Low and high line are stress cases for that reason, not loss cases.

**Paralleling two bridges changes nothing under the retained model.** The drop
term is identical whether the current splits ideally or runs entirely in one
bridge, because a junction drop does not respond to current sharing. Only the
*unmeasured* forward slope responds, by a factor of two in the favourable
direction. So the credible benefit of paralleling is thermal spreading, and the
credible risk is current and thermal imbalance; the conduction claim cannot be
made without the slope.

**The boost stage may be the larger lever, and it is the one this study cannot
bound.** At 50 ns edges the overlap term alone (33.898 W) exceeds the whole
bridge drop (28.304 W). Across the loss budget's design band of 20-100 ns edges
and 50/100 mOhm, that term spans 20.651-81.980 W. It is a sensitivity, not a
prediction about the authored `STW65N65DM2`, whose exact order code is still
unresolved.

## Screening statement per candidate

| Candidate | Screen | Why |
| --- | --- | --- |
| 1. Keep bridge, improve thermal path | **open, lowest risk** | Moves heat only; the electrical term is unchanged by copper, via or heatsink work |
| 2. Larger / lower-drop passive bridge | **blocked on sourcing** | Worth 2.696 W per 0.1 V, so a substitute can be scored the moment an exact orderable part with a drop curve exists |
| 3. Parallel passive bridges | **not justified yet** | Predicts no conduction benefit at all under a constant-drop model; needs measured sharing and the forward slope |
| 4. Active rectifier | **indeterminate, and inverts** | 22.500 W at the 25 °C maximum is below the passive bridge; 45.000 W at the assumed hot value is above it. It also adds gate drive, isolation, dead time, startup-state and EMI obligations |
| 5. Boost-stage optimization | **largest unresolved term** | Overlap sensitivity already exceeds the bridge drop; resolving it needs the exact part and real gate-drive waveforms |

Case 4's numbers are not a discrimination. The hot case computes the *same*
semiconductor terms as nominal for every candidate, because the CCM model
carries copper temperature only; hot forward drop, hot `RDS(on)` and hot core
loss are not modelled. The screen says so in its own output rather than
presenting a case that looks informative and is not.

## What this does not establish

The screen adds no thermal verdict. Loss reduction and thermal closure are
separate results: heat still has to be assigned to a sink, board or air path,
and the harness bridge-thermal and physical-model checks own that FEM evidence.
A green native DRC remains unrelated to thermal acceptance. No candidate here
is qualified, purchased, fabricated or measured.

The 19 unresolved terms are emitted in full in the run report, under
`candidates.unresolved_terms`, and they are also the reported coverage gaps. The
screen cannot reach a pass while any of them is open.

## Rules

| Rule | Meaning |
| --- | --- |
| `ERC.PFC.CANDIDATE_SOURCE_BINDING` | Bridge, boost switch, SiC diode, inductor, shunt and bypass identities rechecked; every computed term binds to a retained source value |
| `ERC.PFC.CANDIDATE_COVERAGE` | Every candidate/case term is computed or explicitly unresolved |
| `THERMAL.PFC.CANDIDATE_CLOSURE` | No candidate assigns its heat to an assembly path here |

All three are in the runner's required set for `power-entry`, so removing the
hook fails coverage instead of silently shrinking the check set.

## Reproducing

```sh
cd zapote
KPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9
cargo run --release --quiet --locked --bin zapote-unit-run -- \
  power-entry/shunt-repair/units.json \
  validation/runs/<new-dir> /opt/homebrew/bin/kicad-cli "$KPY" --all
```

Use `power-entry/shunt-repair/units.json` for the maintained shunt-repair
candidate; the default `validation/units.json` registry intentionally retains
its historical board and does not carry this candidate.

Use `--release`. The power-entry stage replays retained FEM meshes (about
1.2 GB across `bridge-thermal-02` and `shunt-assembly/run-15`), and a debug build
is roughly an order of magnitude slower on them: a debug run had not finished
its power-entry stage after 25 minutes, while the same run in release completes
the whole seven-unit suite in about five minutes. `suite-identity.json` records
the executable hash, so the profile used is visible in the retained evidence.

Two invalid instrument runs are retained locally under
`validation/runs/candidates-invalid-*`: one invoked the KiCad extractor with a
Python that has no `pcbnew`, and one ran without main-display access (KiCad's
framework Python needs it). Both failed closed with a runner error rather than
producing a plausible-looking result. `validation/runs/` is Git-ignored, so
these are local records, not checkout contents.
