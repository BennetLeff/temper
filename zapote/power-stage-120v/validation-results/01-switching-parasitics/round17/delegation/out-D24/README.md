# D24 — recovery sensitivity and S4 decision

**c — Every completed tested S4 model case fails, but the physical decision still needs one synchronized S4 commutation-waveform measurement: off-device die-equivalent VGS must stay below 1.9 V and both die-equivalent VDS peaks at or below 520 V over the specified corners.**

This is **simulation evidence**, not a measured silicon result. No passing
recovery boundary was found in the tested transit-time family. The missing
physical range prevents claiming (a) “every plausible recovery fails” or (b)
“every plausible recovery passes.” In particular, no defensible single Qrr,
trr, Irrm or softness threshold follows from these results. F6 or another
remedy remains justified by the model failures, but this study cannot prove
that the bench is irrelevant or authorize a particular circuit change.

## Identity and method

Base: `c09244caa7588bb72d786a8b1b884390003a5caf`, branch
`codex/ps-r17-d24-recovery`. Inputs are the current D2 deck and
`d2/legA-h0-best.matrix.txt`; no board, netlist, firmware, matrix, upstream
runner or model source was edited. The D2 output-resistance driver remains
5 Ω pull-up / 0.55 Ω pull-down, 3.9 Ω external gate resistance and 15 V drive.
The independent D23 driver-model work is not incorporated.

[run.py](run.py) imports the existing D2 matrix converter, D3 recovery
postprocessor and kit ngspice runner read-only. It changes the vendor-fetch
and temporary-run destinations to this folder's ignored `cache/`. A generated
[s4.cir](s4.cir) differs from D2 only by a global junction-temperature parameter
and `.temp`. D2's existing `ITL4=100000` is retained. Each completed simulation
has both measurement and raw runs, checked return codes, full end-time checks,
solver logs, parameters and a losslessly compressed, full-adaptive-resolution
transition CSV. Licensed model files are never included in committed output.
[fetch_models.sh](fetch_models.sh) retains the upstream archive/library SHA-256
checks and places downloads only in the ignored cache.

The recovery fixture is unchanged D3: 400 V, 58.2 A, equal 730 Ω gate
resistors, initial load ramp, then commutation. At 25°C the nominal model's
zero-crossing slew is about 100.6 A/µs. It is not an exact replica of the
manufacturer's unspecified fixture. At 150°C the same fixed gate resistor
produces about 87.7 A/µs for the nominal model; the hot map is therefore an
**exploratory fixed-fixture temperature comparison**, not a 100 A/µs hot
characterization. Actual slew appears in [sweep-table.csv](sweep-table.csv).

Only `cool_tech_w3.fpar20` (diode TT, originally 50 ns) is changed in local
copies, for both devices. The pinned original's bytes remain untouched.
Before/after values and derivative hashes are in the `*-provenance.json`
files and each case's `identity`. There is no independent softness knob in
the L1 subcircuit. Diode forward-law parameters and nonlinear Coss/Cgd are
fixed; altering them would require a separate source-backed model
calibration. See [sources.md](sources.md) for the complete parameter/line map.

## Plausible-range evidence and its limit

[Sources and applicability](sources.md) separates genuine component limits
from exploratory model values. Infineon's selected-part Table 7 specifies,
at 25°C / 400 V / 58.2 A / 100 A/µs, Qrr typical 2.30 µC and maximum 4.60 µC,
trr typical 236 ns and maximum 354 ns, and Irrm typical 15 A with no maximum.
There is no minimum Qrr or published softness interval. Typical is not a
lower bound. Family application-note curves and published EPE 2021 recovery
traces provide mechanism evidence, but do not supply a transferable hot,
high-slew tolerance for IPW65R018CFD7.

The recovery map includes TT 0, 25, 50, 100, 125, 200, 260, 400 and 800 ns.
The S4 screen uses the original 50 ns, near-typical 125 ns, intermediate
200 ns, and near-maximum-charge 260 ns variants; TT=0 is a diagnostic control.
The 400/800 ns maps exceed the datasheet charge/time maxima and are explicitly
excluded from the constrained subset. These parameter values are **chosen
sensitivity samples**, not manufacturer parameter bounds. Even the
max-compatible samples cannot establish a production envelope at S4 slew and
temperature.

| TT (ns) | 25°C Qrr (µC) | trr (ns) | Irrm (A) | tb10/ta | Meaning |
| ---: | ---: | ---: | ---: | ---: | --- |
| 0 | 1.61236 | 205.829 | 11.6993 | 0.222649 | Zero transit-time storage; output charge remains |
| 50 | 1.73882 | 209.958 | 12.3023 | 0.239345 | Unmodified vendor model; reproduces D3 |
| 125 | 2.35560 | 230.968 | 15.6173 | 0.253354 | Near the three published typical values |
| 200 | 3.41597 | 266.298 | 21.0257 | 0.211361 | Below Qrr/trr maxima; no Irrm maximum specified |
| 260 | 4.52523 | 299.983 | 25.9732 | 0.173992 | Near Qrr maximum, below trr maximum |
| 400 | 7.79748 | 383.259 | 37.8283 | 0.115152 | Outside both maxima; diagnostic only |
| 800 | 20.34592 | 599.934 | 68.4310 | 0.045460 | Outside both maxima; diagnostic only |

Values come from [the initial map](map-tt0,25,50,100,200,400,800-step0.2.json)
and [near-limit map](map-tt125,260-step0.2.json), using D3's stated terminal
charge convention. The original model's internal body branch contributes
0.12218 µC over its 1.73882 µC terminal recovery window; at TT=260 ns the
internal contribution is 2.89210 µC. These are model branch diagnostics, not
independent silicon measurements. The zero-TT terminal pulse cannot be
called “no reverse recovery,” and the low-softness output cannot be assigned
to minority-carrier snap-off alone.

## S4 sweep and numerical verification

Every transit-time screen covers the requested 16 cases: 198/280 V, DIR0/1,
capacitor ESL 1.06/10 nH and 27/150°C; IL=-20 A and DT=443 ns throughout.
The 1.9 V screen is applied at both temperatures as the brief requests.
Per-case VDS and off-gate values, statuses and timestep are in
[sweep-table.csv](sweep-table.csv); aggregates and independent CSV
recomputation are in [audit.json](audit.json). This sampled grid is not a
mathematical proof over continuous parameter values.

Final accounting: **105 completed simulations** (82 coarse S4 + four S4
refinements + 19 recovery fixtures). **All 86 completed S4 simulations fail**;
80 coarse cases cover the five admissibility-screen/control TT values and all
16 requested corners each. Two additional completed TT400 diagnostics are
outside the datasheet-max-compatible subset. There is **one deliberately
interrupted indeterminate diagnostic**, no spontaneous solver aborts,
and **29 planned diagnostics not run**. These categories are kept separate.

| TT (ns) | Complete coarse cases | Pass | VDS min–max (V) | Off-gate min–max (V) |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 16 | 0 | 395.9556–464.3684 | 2.942232–3.468751 |
| 50 | 16 | 0 | 441.6644–513.0911 | 3.473475–4.182724 |
| 125 | 16 | 0 | 555.1390–600.2673 | 4.319732–5.398770 |
| 200 | 16 | 0 | 608.2592–793.5515 | 4.754352–6.056712 |
| 260 | 16 | 0 | 653.5084–809.4570 | 4.924955–6.262266 |
| 400 | 2 | 0 | 723.7448–810.8310 | 6.195741–6.418255 |

At TT=0 all 16 cases fail off-gate, despite VDS remaining below 520 V:
off-gate 2.942232–3.468751 V, VDS 395.9556–464.3684 V. At unmodified TT=50 ns,
all 16 fail off-gate: 3.473475–4.182724 V, VDS 441.6644–513.0911 V. Increasing
stored charge does not reveal a passing boundary in the completed tests.
The severe peaks of larger-TT cases are failure-screen indications; the
model is not a validated repetitive-avalanche or destruction predictor.

The eight matching cold `grid-best-longdt` S4 rows reproduce exactly at printed
precision. Seven complete matching D13 cold/hot baseline comparisons differ
by at most 0.6 mV VDS and zero printed gate voltage. The small D13 differences
are retained, not rounded away; the audit uses a disclosed 1 mV / 10 µV
reproduction tolerance. D13's 150°C /198 V /DIR1 /ESL10 case was historically
indeterminate and is not used as a numerical reference; the current D24 run
completes. This exclusion does not turn that historical abort into a pass.

[refine.py](refine.py) checks four S4 probes at 0.1 ns versus 0.2 ns: the
smallest off-gate control, highest stock-model VDS, near-typical charge,
and high-charge hot corner. It also checks the 260 ns recovery-map point at
half timestep. These are bounded numerical checks, not whole-grid refinement
or silicon-model validation. All four verdicts remain FAIL; the largest absolute VDS movement is 2.2394 V
and the largest off-gate movement is 4.179 mV. The 260 ns map Qrr changes
from 4.525233835 to 4.525170502 µC (−0.00140%). Exact changes are in
[refinement.json](refinement.json) and [audit.json](audit.json).

The deliberately stopped out-of-range diagnostic is **INDETERMINATE**:
[out-of-range-interruption.json](out-of-range-interruption.json) records its
command, parameters, vendor hash and process interruption. Two TT400 ns
cases completed and failed before the third was interrupted. That third
case's partial raw file and inputs are retained under `interrupted/`; no
partial peak is accepted. The remaining 29 TT400/800 corners were **not run**,
not counted as aborts or passes. The reason for stopping is the completed
recovery map already placing those settings outside both datasheet maxima.

## One decisive measurement, specified

**Synchronized S4 double-pulse commutation capture** on the selected
IPW65R018CFD7 leg with the actual UCC21550 gate network: establish 20 A body-diode
forward current, turn on the opposing switch with 443 ns effective command
gap, and simultaneously capture recovering-device terminal current, both
VDS and recovering-device VGS. Repeat that one measurement protocol at
198/280 V, both directions, measured effective capacitor ESL 1.06/10 nH,
and junction 27/150°C, using the board-equivalent commutation and gate loops.
Record actual gate timing and slew; matching only Qrr at the slow datasheet
point is insufficient.

The **decisive thresholds for this screen** are the maximum die-equivalent
off-device VGS **<1.9 V** and each die-equivalent VDS **≤520 V** in every
requested corner. Use simultaneous traces and validated package/probe
correction with uncertainty to relate TO-247 terminal probes to die quantities;
a terminal-only measurement without that relation does not close a die-voltage
criterion. Exceeding either threshold establishes a needed remedy for this
S4 screen. A pass requires the uncertainty-inclusive values to meet both
screens over the corners, not merely one nominal waveform. It does not close
other operating regions or safety qualification.

This is one named waveform measurement protocol with two existing acceptance
thresholds, **not an invented universal softness threshold**. Its current
trace also supplies Qrr, Irrm, trr and tb10/ta for model calibration, but those
scalars alone cannot determine the peak gate response to a waveform. The
specified source/parameter gap remains open until that waveform or a
vendor-validated high-slew/hot model supplies it. No actual measurement was
performed in D24.

## Reproduce

From the repository root with Miniforge Python/NumPy/Matplotlib and ngspice:

```sh
P=zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D24
zsh "$P/fetch_models.sh"
PYTHONDONTWRITEBYTECODE=1 python3 "$P/run.py" smoke
PYTHONDONTWRITEBYTECODE=1 python3 "$P/run.py" map
PYTHONDONTWRITEBYTECODE=1 python3 "$P/run.py" map --tt 125,260
PYTHONDONTWRITEBYTECODE=1 python3 "$P/run.py" sweep --tt 0,50,125,200,260
PYTHONDONTWRITEBYTECODE=1 python3 "$P/refine.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$P/audit.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$P/verify.py"
ruff check --no-cache "$P"/*.py
```

The original exploratory command also scheduled TT400/800 S4 diagnostics;
it was deliberately interrupted as documented above and is not required to
regenerate the constrained result. Each numerical input is hash-bound in
case records and provenance. The smoke test passed. No Rust/native bridge
build was needed. Current write scope is only this `out-D24` folder; parent
coordination owns commits, push and PR publication.

Final verification: [audit.log](audit.log) recomputes all 105 completed
transition records and preserves the indeterminate count;
[verification.json](verification.json) checks 27 recorded input hashes and
licensed-file exclusion; [lint.log](lint.log) is clean. The runner and
refinement scripts received formatting/import-order cleanup only after runs
finished. Exact executed sources are preserved as
[run-executed.py.txt](run-executed.py.txt) and
[refine-executed.py.txt](refine-executed.py.txt), matching the historical
runner hashes. [format-equivalence.json](format-equivalence.json) verifies
AST equality except ordering within contiguous import blocks. They can also
be executed directly with Python if exact historical source bytes are needed.
The provenance verifier checks the retained campaign; new remeasurement
outputs should be reviewed as a new campaign, not silently repinned.
