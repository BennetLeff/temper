# D26 — catalog driver timing scenarios

**INDETERMINATE as a physical gate-timing qualification: the catalog timing scenarios run, but the output-stage surrogate misses TI's loaded-edge/current fixtures and some switching cases abort; this evidence cannot establish a guaranteed 391–498 ns gate-threshold window or overturn F7/S4 decisions.**

The completed six S1 and five S2 cases retain their 1.9 V off-gate, 520 V VDS and ZVS screens. All twelve S4 cases abort numerically, so this work supplies no new S4 waveform verdict. All 36 selected approximation baselines reproduce their native-19 reference rows.

This is an original behavioral ngspice model of the catalog **UCC21550BDWKR**,
using TI **SLUSE89C**. It contains no TI proprietary source. Worktree base is
`27b23b5ea01ee983d651c9461b648cf2d123f575`; native-19's best leg-A matrix is
the circuit identity. No board, netlist, firmware or native bridge was changed.
The power-review and Python skills were applied. All evidence and caches stay
inside this folder.

[Parameter ledger](PARAMETERS.md) cites the catalog datasheet pages, figures,
limits and conditions. [Numerical summary](SUMMARY.md), [case table](CASES.md),
[fixtures](FIXTURES.md), [verification](verification.json), and
[provenance](provenance.json) give the results. Every completed or numerically aborted campaign case retains its executed
`runs/<tag>/deck.cir`, solver `run.log`, status and full-precision compressed
`wave.txt.gz` when a waveform exists. Aborts remain **INDETERMINATE**, even when
ngspice's control-language `quit` makes its process return zero.

## What was actually tested

The required campaign comprises36 min/typ/max model cases and36 matching
approximation baselines: S1=(170V,37A), S2=(280V,71A), S4=(198V,−20A), both
commutation directions, capacitor ESL1.06/10nH. The baseline uses the exact
391/443/498ns ideal gaps from the corresponding native19-carryover JSON rows.
It does not claim to rerun every voltage/current point in that larger grid.
The model inputs have200ns complementary gaps; RDT=49.9kΩ, with±0.1%
tolerance applied at the min/max scenarios. All MOSFET solves use ngspice's
27°C default; the1.9V criterion is a hot-threshold **screen**, not a hot
MOSFET simulation. Gate supply15V and all other D2 power-circuit values remain
unchanged. Ideal, precharged supplies exclude bootstrap droop and startup
sequencing from this commutation campaign.

Independent skew/PWD sampling supplements the symmetric corners. The attempted
subset in `stress.json` is the authoritative coverage; the larger optional
96-case space was stopped to prioritize the full required campaign. It is
not an exhaustive corner proof. Each attempted run has a90second wall limit.
The scheduler switch preserved two interrupted diagnostic directories and accepted no result
from them. Their stdout was held in supervisor pipes and was not recoverable
after interruption; only deck and explicit interrupted status survive. The
required target interrupted during rescheduling was subsequently attempted in
the final campaign; no missing diagnostic log is represented as solver evidence. No numerical retries or physics changes were used to turn aborted
cases green.

## Timing reference planes and crossings

TI defines driver dead time from the outgoing **output90% falling** crossing
to the incoming **output10% rising** crossing (SLUSE89C Fig6-4,p19). The
model separately reports this at the actual loaded driver pins.

The MOSFET numbers use **die-equivalent** nodes inside the pinned Infineon L1
model. For each of1.9,3.0 and7.5V, gate dead time is the first incoming upward
crossing minus the first outgoing downward crossing after2µs. The full
2…3.193µs window records both devices' crossing counts and whether both are
above that threshold inside the chosen gap. More than one crossing is flagged
as ringing/re-crossing; a first-crossing number alone is not a sustained
safe-off claim. 7.5V is a50% diagnostic, not a conduction threshold.

Off-gate peak is measured from the incoming driver's10% crossing through
3.193µs. Both die-VDS peaks use2…3.193µs. ZVS retains D2's incoming-VDS≤5%
ofbus criterion, sampled at the incoming driver's10% crossing. That is a
different time from the old ideal-command sample; baseline reproduction uses
the **original** command-time and per-gap windows separately. Results cannot
be compared by accidentally mixing those reference planes.

FINDINGS F7's391–498ns range was swept as D2's **ideal command gap**; its
separate396.6–488.0ns resistor estimate is not a measured VGS crossing window.
The baseline itself yields substantially shorter3V die-VGS dead time.
Consequently, observing a threshold gap below391ns does not on its own
contradict F7 or imply overlapping conducting devices. Its hot-screen and
S4 qualification requirements remain in force.

## Model construction and fixture misses

[Model](ucc21550_parametric.lib) uses hysteretic input switches, XSPICE
inertial pulse filters, transport propagation delays, an opposite-input
holdoff implementing the longer-of rule, and B-source output conductances.
`CORNER=-1/0/+1` selects min/typ/max; ngspice subcircuit parameters are numeric,
so these are the documented equivalents of min/typ/max names. Primary GND
must be simulator ground. Thresholds and pull resistances use typical values;
their uncertain correlation is not invented by assigning all minima together.

The initially observed~3ns unloaded propagation offset was corrected by
**analytical reference-plane accounting**, before decision runs. With effective
rising pull-up resistanceRb=5Ω||1.47Ω and sinkRl=0.55Ω, the10% output crossing
occurs at control fraction `0.1Rb/(0.9Rl+0.1Rb)`. The90% falling crossing uses
`0.1Rl/(0.9Rh+0.1Rl)` of the falling ramp. Those fractions of the5ns control
ramp, plus explicit ADC bridge delay, are subtracted from transport delay.
This was not a fit to switching results. Initial fixture summary is preserved
in `fixtures-before-reference-correction.json`; final raw fixture runs support
the final claims. The temporary boost is prohibited from reactivating during
falling control ramps.

The typical-only output surrogate deliberately remains unqualified:

- Transient NMOS assistance is1.47Ω in parallel with5Ω for an **assumed20ns**.
  Its duration, nonlinear drive and production/temperature range are absent
  from the catalog data. The5ns control ramp is also assumed.
- The1.8nF fixture yields about3.85ns rise and3.93ns fall, versus TI's typical
  8ns/8ns. These fail the stated±20% fixture tolerance. The model was not
  tuned to erase these misses.
- Peak capacitive current exceeds TI's4A/6A typical measurements. Those
  typical entries are not guaranteed clamps; clipping the model to them
  would invent a physical bound. DC5Ω/0.55Ω agreement does not validate
  transient current.
- UVLO thresholds are nominal hysteretic levels; selectable delay scenarios
  use the catalog table. VDD-on delay uses the only specified10µs maximum,
  explicitly not a typical. Deglitch and propagation are combined, and
  unpowered active pull-down, isolation CMTI upset, ESD, supply-current paths
  and internal rail overshoot are not modeled.
- DT at49.9kΩ±tolerance is an interpolation from the specified20/50kΩ
  points and the typical equation. It is not a new guaranteed datasheet row.

Independent cold matching±6.5ns and PWD±5ns are applied with35.5ns center
delay, so all edge delays lie within26.5–44.5ns while programmed DT is varied
independently. This avoids the invalid26ns/45ns same-channel pairing and
exposes skew rather than cancelling common-mode delay. Pulse rejection stays
at its12ns typical in these sensitivity samples. None of these sampled timing
combinations can compensate for an unbounded or fixture-failing output stage.

## Reproduction and evidence identity

Use Miniforge Python with NumPy and ngspice45.2:

```sh
cd zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D26
zsh fetch_models.sh
PYTHONDONTWRITEBYTECODE=1 /Users/bennet/Miniforge3/bin/python3 smoke.py
PYTHONDONTWRITEBYTECODE=1 /Users/bennet/Miniforge3/bin/python3 run.py fixtures
PYTHONDONTWRITEBYTECODE=1 /Users/bennet/Miniforge3/bin/python3 extra_fixtures.py
PYTHONDONTWRITEBYTECODE=1 /Users/bennet/Miniforge3/bin/python3 output_fixtures.py
PYTHONDONTWRITEBYTECODE=1 /Users/bennet/Miniforge3/bin/python3 run.py baseline
PYTHONDONTWRITEBYTECODE=1 /Users/bennet/Miniforge3/bin/python3 run.py model
PYTHONDONTWRITEBYTECODE=1 /Users/bennet/Miniforge3/bin/python3 report.py
```

`run.py stress` additionally attempts/resumes the full optional96-case grid;
it exceeds the original limited stress coverage. It is not needed to establish
that the physical bound remains unavailable. Vendor archive/library hashes
are checked before switching solves, and the original kit smoke suite passes.
Licensed models remain only in ignored`vendor/`. Logs and waveforms are
explicitly unignored and verified for inclusion.

The first campaign began before strict cache identities were added. Its
provenance therefore explicitly labels the final source hashes as **post-run
reconstructed**, validates saved executed decks against the final renderer,
and does not pretend an execution-time runner hash was captured. Future reuse
requires exact deck/model/vendor/matrix/runner/options/solver identities; unmatched old runs
are preserved under`runs/previous-*` before rerunning. No firmware or Rust
build/test was appropriate to this simulation-only scope.
