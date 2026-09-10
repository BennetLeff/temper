# LMR51430XDDCR model and simulation audit

Date: 2026-09-09  
Checkout: `ce344553c3d4aface00a554c99e78a0ccd9fd8f1`  
Simulator available: `/opt/homebrew/bin/ngspice`, ngspice-45.2

## Result

Stage-3 simulation qualification is blocked. No downloadable, exact-device
model for `LMR51430XDDCR` (500 kHz PFM) was found in TI's official product
page/model catalog, and no model bytes or license were therefore available to
hash or test. The normal simulation host must remain blocked until a reviewed
exact model manifest and qualification receipt exist. Product limits currently
contain 20 unresolved requirements; these exploratory attempts do not close
any of them and do not claim a pass.

The target identity matters: `LMR51430XDDCR` is the 500 kHz PFM orderable. The
500 kHz FPWM sibling is `LMR51430XFDDCR`; 1.1 MHz variants are also different
devices for simulation identity. TI's current product page describes the
family as 4.5–36 V input, 3 A continuous output, 0.6 V minimum output/reference
domain, 500 kHz and 1.1 MHz fixed-frequency options, PFM and FPWM options,
fixed soft start, and protection features. See:

* [TI LMR51430 product page](https://www.ti.com/product/LMR51430)
* [TI LMR51430 datasheet Rev. A](https://www.ti.com/lit/ds/symlink/lmr51430.pdf)
* [TI E2E model availability response](https://e2e.ti.com/support/tools/simulation-hardware-system-design-tools-group/sim-hw-system-design/f/simulation-hardware-system-design-tools-forum/1238369/pspice-for-ti-lmr51430xf-transient-model-does-not-exist-in-pspice---ti-library)

The E2E response concerns the FPWM sibling, so it is corroborating evidence
about TI's published model availability, not permission to substitute that
variant for XDDCR.

## WEBENCH vendor route

The linked TI WEBENCH Power Designer route was opened in Chrome at:

https://webench.ti.com/power-designer/switching-regulator?base_pn=LMR51430&litsection=features&origin=ODS

TI documentation confirms that WEBENCH uses a SPICE engine and supports
startup, input transient, load transient, steady-state, and Bode simulations;
see the [WEBENCH exercise book](https://www.ti.com/lit/ug/ssqu018/ssqu018.pdf)
and [WEBENCH overview](https://webench.ti.com/help/PowerDesigner/Overview.htm).
This is a legitimate vendor-supported transient-simulation route in principle,
not merely a design-calculation page.

The exact-device lookup was tested without logging in or accepting terms:

* `LMR51430XDDCR` returned `Sorry, we could not find "LMR51430XDDCR"`.
* Family input `LMR51430` offered only `LMR51430X (Buck)`, `LMR51430XF
  (Buck)`, `LMR51430Y (Buck)`, and `LMR51430YF (Buck)`.
* Selecting `LMR51430X (Buck)` auto-filled family-level limits (4.5–36 V,
  3 A; output range 0.6–28 V), but exposed no XDDCR package/orderable
  identity or exact model bytes.
* `View Design LMR51430X` remained disabled until the WEBENCH/TI terms
  checkbox was selected. Terms were deliberately not accepted and no design
  was submitted.

Thus WEBENCH establishes a possible vendor transient-simulation path, but this
session could not establish exact XDDCR/PFM identity, export a model or
waveforms, or create qualification evidence. The stage-3 blocker remains.

## Exact model search and compatibility

The TI product page was inspected for PSpice average, transient, and
unencrypted model entries for `LMR51430`, `LMR51430XDDCR`, and `LMR51430XF`.
No such entry or downloadable archive was exposed. The TI E2E answer says the
available models are the ones on the device page. Consequently:

* exact model source URL/version: unavailable;
* exact model bytes and SHA-256: unavailable;
* model license/terms: unavailable;
* ngspice syntax/compatibility: untestable because no exact file exists;
* PFM/500 kHz behavior: unverified;
* switching, enable/startup, current limit/hiccup, and loss behavior:
  unverified.

The checked-in `simulation/models/LMR51430_avg.lib` was retained as a negative
control only. Its SHA-256 is
`d8c719dcdec4078ccc174fb30cc5890666ae09d965f4356d2c4aa2a086861cc6`. It
declares a 0.8 V reference and an averaged voltage-controlled source, without
switching, enable/startup, protection, or a credible input-power/loss path.
It cannot qualify this exact device and was not used in the attempts below.

## Circuit values and source status

The candidate circuit identity is the existing `harness-lab/engineering/buck.ato`
entry instantiating `elec/src/modules.ato::BuckConverter3V3`; the component
values below are from `harness-lab/engineering/circuit-contract.json`, which
binds the MPN and PCB nets. They are circuit inputs, not simulation validation.

| Item | Exact candidate value | Source/status |
|---|---:|---|
| VIN / VOUT | 15 V / 3.3 V | Temper circuit source; output assertion is ±5% |
| C9 input | 10 µF, 25 V, ±20% | Murata `GRM32ER71E106KA12L`; DC-bias effective C unresolved |
| C10 bootstrap | 100 nF, 25 V | `C0603C104K5RACTU`; model behavior unresolved |
| L2 output | 5.6 µH | Bourns `SRP1265A-5R6M`; contract gives 12.5 A rating, but required saturation evidence remains unresolved |
| C11/C12 output | 22 µF each, 25 V, ±20% | Murata `GRM32ER71E226KE15L`; effective combined C under bias/tolerance unresolved |
| C13 HF output | 100 nF, 10 V, ±10% | `C0603C104K5RACTU` |
| Feedback top/bottom | 100 kΩ / 22.1 kΩ, ±1% | `RC0603FR-07100KL` / `RC0603FR-0722K1L`; sets approximately 3.31 V using 0.6 V nominal reference |

The datasheet's component-design and layout guidance is the relevant source
for the external network, but the requirements receipt still marks effective
capacitance and inductor saturation assumptions unresolved. No missing values
were invented for those fields.

## Missing-model preflight probes (not electrical scenario runs)

Three standalone preflight decks were created with the exact model include path
`../sources/model/LMR51430XDDCR.lib`. Each was run from a fresh attempt
directory using ngspice-45.2 with `-b -r waveform.raw`; each exited `1` before
parsing the circuit because the exact model file is absent. No waveform was
produced, and no electrical metric was measured. These are missing-model
preflight probes only; startup, input-variation, and load-variation tests were
not performed.

| Scenario | Deck | Exit | Retained stderr SHA-256 | Outcome |
|---|---|---:|---|---|
| startup | `scenarios/startup.cir` | 1 | `80761f13b04de83405983150e70e07fcd8002a8394d769351c9516a8fedb9493` | blocked: include file absent |
| input variation | `scenarios/input_variation.cir` | 1 | `ca988897c03cb1dc69f88c7f34111ceaf7216348b5c746e288f7f5768b1d9740` | blocked: include file absent |
| load variation | `scenarios/load_variation.cir` | 1 | `3199b45927c68a579a95c85f16c91deefd4450cd7ba263e2284bd1780bfa3878` | blocked: include file absent |

The retained logs say `Error: Could not find include file
../sources/model/LMR51430XDDCR.lib` followed by `ERROR: fatal error in
ngspice, exit(1)`. The probes use nominal 15 V input, 3.3 V resistive/load
targets, 5.6 µH, 10 µF input capacitance, 44 µF nominal output capacitance,
and the contract's feedback values only to make the blocked attempt
reproducible. They are exploratory controls, not qualified scenarios.

## Actionable unblock

Acquire a TI-supplied exact `LMR51430XDDCR` model with its source URL/version,
license/terms, exact bytes, and pin/orderable identity. Confirm whether it is
encrypted PSpice or unencrypted and whether ngspice can parse it. If encrypted
or otherwise incompatible, the owner must obtain an explicitly supported
simulation route (for example a vendor-supported simulator) or record the
incompatibility as a continuing blocker. After a usable model exists, validate
the three decks against independent datasheet/EVM or bench evidence, pin the
model and evidence hashes, resolve the 20 requirement gaps relevant to
simulation, and only then create the reviewed approval receipt consumed by
`simulation_host.py`.

## Datasheet-derived approximate model run (unqualified)

At the user's direction, `sources/model/LMR51430XDDCR_datasheet_approx.lib`
was added. Its SHA-256 is
`8a8a1bdc7481b35346cb84b2a7e66c1d18fbfcbd0a280363f51052ac9b60e19e`.
The pinned TI datasheet PDF is `sources/datasheet/lmr51430-revA.pdf`, SHA-256
`f7d8053844fb07ae773844f023373c0c570507ca61603fe28dda15364987296c`.

The model is explicitly behavioral: finite-Ron/Roff physical high/low switch
paths, a 500 kHz sawtooth, FB-driven bounded duty, 4 ms reference ramp,
nominal 0.6 V FB reference, nominal switch resistances, and a simple PFM
pulse-inhibit/zero-current approximation. Internal compensation, detailed
peak-current latch/slope compensation, bootstrap timing, dead time,
current-limit/hiccup, thermal behavior, and loss versus temperature are
unsupported assumptions. It is not a TI vendor model and is not physically
qualified.

The three scenario decks now run against this model; earlier missing-include
logs remain as preflight evidence and are not counted as scenario tests. Runs
used ngspice-45.2, 200 ns nominal maximum step, 8 ms duration, 10 µF input,
44 µF output, 100 nF CB-to-SW, 100 kΩ/22.1 kΩ feedback, 5.6 µH output
inductor with 10 mΩ assumed DCR, and 100 mΩ source resistance. Load variation
is an exploratory 0.05→0.5 A step, not a product limit.

| Run | VOUT min/max | Last 1 ms mean | Inductor current min/max | Mean 6–8 ms gate edge rate | Result |
|---|---:|---:|---:|---:|---|
| startup, VIN ramp + EN delay | ~0/3.362 V | 3.284 V | −0.884/6.252 A | 497 kHz | model run; no qualification |
| input, 13.5→16.5 V request (deck reaches 15 V by 8 ms) | ~0/3.364 V | 3.284 V | −0.883/1.905 A | 484 kHz | model run; no qualification |
| load, 0.05→0.5 A at 5 ms | −10 µV/3.364 V | 3.284 V | −0.888/1.898 A | 490 kHz | model run; no qualification |

Raw waveform files and separate logs are retained beside each deck under
`scenarios/*-attempt/`. Adaptive transient refinement produced more points
than the nominal 200 ns step near switching edges; rates above count high-side
gate crossings only in the 6–8 ms window. Negative inductor-current
excursions and the startup peak are limitations of this approximation and
require independent review.

## Distinct datasheet holdout

`scenarios/datasheet_holdout.cir` uses a separate 12 V→5 V, 0.5 A point with
8.2 µH and 44 µF, 100 kΩ/13.7 kΩ feedback, and 8.5 mΩ assumed DCR. It ran to
8 ms with a 500.5 kHz measured gate edge rate; VOUT ranged approximately
0–3.06 V and the last 1 ms mean was 2.95 V. The error versus 5 V shows that
the approximate loop law is not calibrated across designs; this is not a pass
or a datasheet reproduction.
