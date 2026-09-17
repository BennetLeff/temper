# Power-entry re-engineering screen

This screen asks *which architecture lever moves the power-entry loss while the
board carries the same required power*. It is a screening instrument. It does
not complete the five-case matrix on its own — it screens three line points and
names the rest as inputs — and it does not establish that any candidate is
qualified. [The decision record](DECISION.md) carries the case-by-case state.

Rust owns it (`packages/zapote-harness/src/pfc_candidates.rs`) and it runs inside
the common unit runner, so its findings and rule coverage are retained with the
rest of the power-entry evidence instead of being summarized by hand.

## Status

**No candidate is selected, and no architecture is ranked.** The useful output
is a priority order for the next measurement work. Where a comparison would need
a number nobody has measured, the screen reports the threshold that decision
turns on and leaves it open.

Earlier revisions of this screen overstated what it shows in four specific ways
about the comparison itself, and treated a resolvable part identity as an open
question. Those are now fixable claims, and each is addressed below.

## The requirement

The screen fixes a common **required power** and derives the current each line
needs to carry it. The requirement is the ideal CCM model's input power at the
nominal line and the 15 A true-RMS ceiling: **1,796.4 W**.

This is the model's input power. It is not delivered DC power and not pan power.
Converting it to either needs the efficiency, which is itself unresolved and is
named as a required input.

| Line | Required input RMS | 15 A ceiling | Reachable input power | Shortfall | Bridge drop at 1.05 V |
| --- | ---: | --- | ---: | ---: | ---: |
| 108 V | 16.658 A | **binds** | 1,617.1 W | **179.3 W** | 28.309 W |
| 120 V | 15.000 A | met | 1,796.4 W | 0 W | 28.304 W |
| 132 V | 13.645 A | met | 1,796.4 W | 0 W | 25.730 W |

Two things follow directly.

**Low line cannot deliver the requirement at all.** At 108 V it needs 16.658 A
inside a 15 A ceiling. The shortfall is reported (179.3 W), not absorbed, and the
reachable power is 1,617.1 W. So low line is not merely a stress case; it is the
case that fails the requirement.

**The bridge drop falls as line voltage rises**, from 28.309 W at 108 V to
25.730 W at 132 V, because a fixed required power needs less current at a higher
line. This is the opposite of what a fixed-current sweep implies, and it is the
reason the requirement is fixed in power.

## Findings

**The strongest result is that switching behaviour can move the heat budget by
tens of watts.** At the nominal point the boost overlap term is 33.898 W at
50 ns edges, which exceeds the entire bridge drop of 28.304 W, and across the
loss budget's 20-100 ns band it spans tens of watts. That single term outweighs
every bridge-architecture question here, and it is a design sensitivity keyed to
an assumed edge time rather than a statement about the authored device.

**The device identity and a bounded event model are now explicit.** The
authored/native order code is `STW65N65DM2AG`; package marking is `65N65DM2`,
and the source/native/manufacturing receipts bind that identity. Rust models
UCC28180 source/sink limits, Miller plateau, the 10 ohm + 3.3 ohm gate network
and loop inductance across 18 cases. At nominal conditions it reports 43.943 W
overlap, 2.397 W Eoss and 0.155 W gate loss. This remains typical model
evidence; measured waveforms and hot data are required for qualification.

**The active-rectifier question reduces to one number.** The screen reports the
break-even per-device `RDS(on)` at which synchronous conduction would equal the
passive bridge's drop term:

| Line | Passive drop at 1.05 V | Break-even per device | Retained device, 25 °C max |
| --- | ---: | ---: | ---: |
| 108 V | 28.309 W | 62.9 mΩ | 50 mΩ |
| 120 V | 28.304 W | 62.9 mΩ | 50 mΩ |
| 132 V | 25.730 W | 69.1 mΩ | 50 mΩ |

Synchronous rectification pays only if the device's **hot** `RDS(on)` stays under
that threshold. The retained 650 V part's 25 °C maximum sits below it and an
assumed hot value sits above it, so the decision is exactly the unread hot curve.
That is why this stays unresolved instead of ranked.

**Parallel bridges are inconclusive, not rejected.** Under a constant-drop model
the drop term is identical whether the current splits equally or runs entirely
in one bridge. That is a statement about a missing model term, not evidence that
paralleling cannot help. The decision needs the element's forward slope; the
screen reports the slope coefficient it would be applied to (450 W/Ω for one
bridge, 225 W/Ω for two sharing equally at the nominal point) and the imbalance
risk the constant-drop model cannot express.

**A substitute bridge is worth 2.696 W per 0.1 V** of forward drop at the
nominal point. That stays a part-sourcing question and is blocked until an
exact, orderable part exists to score.

## What this screen cannot show

Five inputs are named in the report and no loss term is computed without them:

- hot junction temperature for every semiconductor, not a copper temperature;
- degraded-airflow and installed-heatsink data for the assembly;
- startup, inrush, precharge, shutdown and fault behaviour, for which no CCM
  operating point exists;
- measured switching waveforms for the boost cell: the retained datasheet bounds
  the output-capacitance term, but not the turn-on/turn-off overlap;
- delivered-output efficiency, needed to convert the ideal input power used
  here into delivered DC or pan power.

Only the three line voltages appear as operating points in this screen, and a
copper-temperature sweep is not a substitute for a real cooling case. That is a
statement about the screen, not about the project: the hot and degraded-cooling
case is modelled by the bridge joint and cooling instruments
(`shunt-repair/bridge-thermal-02`, `thermal/bridge-cooling.md`), and
[the decision record](DECISION.md) reads them together. Startup and fault remain
genuinely unmodelled everywhere, because no CCM operating point describes them.

## Decision

Pursue **candidates 1 and 5 together**: keep the passive bridge and establish
its practical heatsink path, while resolving the boost MOSFET's switching
losses. These two are compatible and they attack the two things the screen
actually identified, the concentrated bridge heat and the largest unmeasured
term. Candidates 2, 3 and 4 are deferred with their thresholds computed, not
rejected.

[The decision record](DECISION.md) states the choice, the case-by-case state of
the five experiments, what would reverse it, and what is explicitly not
decided. Its short version: the bridge thermal path is already modelled and the
answer is that the bridge is a constraint with 5 K of junction margin at design
and a failed-fan budget 25 K over, while the boost overlap term is still
unbounded and can exceed the whole bridge loss.

The earlier five-candidate framing asked for five board variants up front; that
is not the plan. The plan is one sufficiently complete baseline model that can
support a design decision, and the remaining work is measurement, not another
candidate board.

## Rules

| Rule | Meaning |
| --- | --- |
| `ERC.PFC.CANDIDATE_SOURCE_BINDING` | Bridge, boost switch, SiC diode, inductor, shunt and bypass identities rechecked; every computed term binds to a retained source value |
| `ERC.PFC.CANDIDATE_COVERAGE` | Every required input and unresolved term is named; nothing is zero-filled |
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

The 15 A ceiling, the 1.05 V bridge test point and the 50 mΩ 25 °C maximum are
retained source values. The boost-switch order code, its `Eoss(VDS)` curve and
its `Qg` 120 nC come from the selected ST source and retained
`sources/STW65N65DM2AG.pdf`. The
0.85/1.30 V band and the 100 mΩ hot resistance are explicit sensitivities, and
the output-capacitance term is a digitized typical-curve estimate, never part
guarantees.
