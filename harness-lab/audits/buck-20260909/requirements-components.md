# Buck requirements and component audit (2026-09-09)

This audit is source reconciliation for the engineering reference. It does not
qualify the assembled hardware, approve a product requirement, or authorize a
model trial. The requirements manifest records source-backed values where the
Temper source is unambiguous; values that require a product decision remain
`unresolved`.

## Resolved from Temper sources

| manifest id | value | source and interpretation |
|---|---:|---|
| `vin_nominal` | 15.0 V | `elec/src/modules.ato:1542-1545,1564-1565` declares the isolated 15 V rail feeding the buck. |
| `vin_min` / `vin_max` | 13.5 / 16.5 V | `elec/src/modules.ato:1617` asserts the auxiliary output within 15 V ±10%; these are the buck input envelope implied by that source assertion. This is a rail operating envelope, not the LMR51430 absolute maximum. |
| `vout_nominal` | 3.3 V | `elec/src/modules.ato:1438-1441`; the module's `power_out.voltage` assignment. |
| `vout_tolerance` | 3.135–3.465 V | `elec/src/modules.ato:1528`; explicit 3.3 V ±5% assertion. |
| `iout_continuous` | 0.5 A | `elec/src/modules.ato:1619-1622` calls out “MCU+logic: ~1.5 W (500 mA @ 3.3 V after downstream buck)” as the system budget. This is the only explicit 3V3 load budget found; it is not the IC's 3 A rating. |
| `ambient_temperature` | 0–40 °C normal; 40–70 °C derated | The product requirement is `docs/specs/REQUIREMENTS.md:79-106`: full power is 0–40 °C and derated operation extends to 70 °C. `elec/src/main.ato:490-492` separately declares a 0–50 °C board design ambient; it is not a substitute for the product's normal/derated operating envelope. |
| `inductor_current_rating` | unresolved effective limit | Bourns `SRP1265A-5R6M` datasheet, table on PDF page 1: `Irms=12.5 A` at 40 °C rise and `Isat=23 A` at 20% inductance drop. These are component ratings only; the effective current allowed by the 40–70 °C product envelope, copper, airflow, and converter ripple remains unresolved. |

The manifest resolves four previously null IDs: `vin_min`, `vin_max`,
`iout_continuous`, and `ambient_temperature`. Sixteen mandatory IDs remain unresolved.

## 3V3 and 15V load trace

The 3V3 rail is connected to the MCU (`elec/src/main.ato:918`), the UCC21550
control-side supply (`elec/src/main.ato:798-799` and
`elec/src/modules.ato:370-372`), CT-sense bias (`main.ato:831`), RTD panel
(`main.ato:838`), safety logic (`main.ato:858-859`), and the comparator,
watchdog, UVLO, fault-latch and related logic connected through
`elec/src/main.ato:876-918` and `elec/src/modules.ato:3142-3197,
3235-3358`. None of those declarations gives an individual supply-current
maximum. The only aggregate number is the 500 mA MCU+logic budget cited above.
Consequently, continuous current can be carried as a source-backed system
budget, but peak current, duration, load-step endpoints/slew and transient
limits cannot be derived honestly from this repository.

The 15 V rail feeds the gate-driver secondary/control supply, relay coils and
fan/dropper paths. `elec/src/modules.ato:1619-1623` budgets approximately 2 W
gate drive, 1 W relay coil, and 1.5 W MCU/logic, with an 8 W design budget for
the isolated auxiliary supply. The two relay coils are separately described as
approximately 33 mA each while running at `modules.ato:1168-1169`; the fan is
87 mA maximum at `modules.ato:1629-1654`. These are 15 V upstream consumers,
not 3V3 buck output current, and do not define a 15 V transient or ripple
requirement.

## Conflicts and limits

* `elec/src/components.ato:366-374` and `harness-lab/engineering/circuit-contract.json`
  record the LMR51430's 3 A device rating. `elec/src/constraints.ato:69-73`
  also sets `Power.i_max = 3A`. Neither is a Temper load requirement. The
  source-backed 3V3 budget is 0.5 A; treating 3 A as the product demand would
  be an unsupported sixfold increase.
* The current `AuxSupply` assertion is 15 V ±10% (`modules.ato:1617`), while
  historical generated logs `elec/src/build_output.log:179-181` and
  `build_output_2.log:179-181` display 15 V ±5%. Those logs are not current
  source authority and have no provenance tying them to the present module;
  they must not silently narrow the manifest envelope. A product owner must
  decide whether ±10% is intended before a tighter bench acceptance limit is
  approved.
* `elec/src/main.ato:490-492` sets 50 °C maximum ambient while allowing an
  assertion range up to 60 °C. This does not establish an LMR51430 case or
  junction-temperature limit. The TI device is specified for -40 to 150 °C
  junction and 4.5–36 V input, but those are device operating conditions and
  ratings, not Temper product limits.

## Component and tolerance audit

The exact candidate BOM and pin/net contract are in
`harness-lab/engineering/circuit-contract.json` (sha256
`3993f300a7c0a25b1e02fea37bb5c7608745c14090933d6bec3bfdb20e42524d`). The
source module is `elec/src/modules.ato:1444-1498` and its complete topology is
at `:1500-1526`.

* U3 is `LMR51430XDDCR`, 4.5–36 V input and 3 A continuous device rating. TI's
  datasheet says the 3 A maximum can be derated at high switching frequency or
  ambient; no effective Temper derating has been validated here.
* C9 is Murata `GRM32ER71E106KA12L`, declared 10 µF ±20%, 25 V X7R in the Temper source. The exact
  manufacturer page/specification was not recovered by the host audit; a
  similarly named GRM32D part is not evidence for this GRM32E identity. The
  K tolerance code suggests ±10%, but that inference is not accepted as
  exact-part qualification here.
  C11/C12
  are Murata `GRM32ER71E226KE15L`, nominal 22 µF ±20%, 25 V X7R. Their nominal
  tolerance and voltage rating are source declarations, but no P/N-specific
  DC-bias curve was retained in this checkout. Effective capacitance therefore
  remains unresolved, as required by the manifest.
* C10/C13 are KEMET `C0603C104K5RACTU`, 100 nF ±10%, 50 V X7R per the exact
  K-SIM/spec-sheet source. The circuit's 25 V boot and 10 V output ratings are
  conservative operating declarations. The manufacturer source consulted documents
  that Class-II MLCC capacitance depends on DC bias; no exact curve was
  captured, so nominal 100 nF must not be promoted to effective minimum.
* L2 is Bourns `SRP1265A-5R6M`, 5.6 µH ±20%, 10.0 mΩ max DCR, 12.5 A Irms and
  23 A Isat. Bourns defines Irms as 40 °C temperature rise and Isat as 20%
  inductance drop; those definitions matter more than the bare “12.5 A” label.
* R16/R17 are Yageo `RC0603FR-07100KL` / `RC0603FR-0722K1L`, each declared
  ±1% in the source module and contract. With TI's VFB limits 0.591/0.609 V
  (`modules.ato:1426-1430`), independent ±1% resistor corners give a divider
  output of approximately 3.212–3.420 V (using 99–101 kΩ and 21.879–22.321
  kΩ). Nominal values produce 3.3149 V at 0.6 V VFB, not exactly 3.300 V.
  This fits the existing ±5% assertion, but the tolerance check must include
  VFB and both resistor tolerances; it cannot use only the nominal ratio.

## Requirements still needing a product decision

The unresolved IDs are `iout_peak`, `iout_peak_duration`, `ripple_amplitude`,
`ripple_bandwidth`, `startup_ramp`, `startup_overshoot`,
`startup_settling`, `load_step_endpoints`, `load_step_slew`,
`load_step_undershoot`, `load_step_overshoot`, `load_step_recovery`,
`thermal_limit`, `efficiency_operating_points`, and
`capacitor_effective_value`, and `inductor_current_rating`. In addition, `vin_min/max` should be revisited if
the owner chooses the historical ±5% rail envelope over the current ±10%
assertion. These are not safely inferable from regulator ratings, nominal BOM
values, or the existing layout.

The minimum decisions to unblock a qualified reference are: the accepted 15 V
rail tolerance; a 3V3 peak-load waveform (including duration and slew); ripple
measurement bandwidth and limit; startup and load-step acceptance windows; a
product thermal limit distinct from the 50 °C ambient; efficiency test points;
and whether to obtain capacitor bias curves or specify a conservative measured
effective-capacitance floor. Hardware and component qualification remain
unverified.

## Datasheet-bound electrical margin (not product approval)

For the retained TI LMR51430XDDCR (500 kHz PFM), the datasheet specifies
4.5–36 V VIN, 3 A continuous output capability, 450–560 kHz CCM switching
frequency, and 3.2–5.4 ms internal soft-start. Against the Temper source-backed
13.5–16.5 V input and 0.5 A continuous load, the input envelope has 9.0 V of
lower-side margin above the device minimum and 19.5 V of upper-side margin
below the device maximum; the load budget is 1/6 of the 3 A device headline.
Those margins do not establish transient, thermal, efficiency, or effective
capacitor performance. With L2's 5.6 µH ±20% nominal tolerance, the component
range is 4.48–6.72 µH; current ripple and peak current still require the
switching model and the unresolved load-step endpoints.

## Source identity

Repository source hashes at audit time:

* `elec/src/modules.ato` sha256 `b86344e7c0bd772f9de13d251066a8c9335cfbfaf8014b3d03e1cc78a102edf5`
* `elec/src/components.ato` sha256 `5b00766a2c002291fcd24bb12587766d0e217b1776b87a69676ae7641ea4b764`
* `elec/src/constraints.ato` sha256 `f031aedc6655d61335c6b7ebf3d51eac83a5e66b1302a982299cbf4a6c92e21e`
* `elec/src/main.ato` sha256 `8913d3867b3d694eed1a4db4674c6f3340a95c82d2f610c0828bd8b035294e28`
* `docs/specs/REQUIREMENTS.md` sha256 `497294e9b779cc66e721c3e7107e19e40d1d18e0a6398b28356fda2c0f2cc48c`

Primary manufacturer references are recorded under `sources/`, including the
downloaded TI and Bourns PDFs and their hashes in `sources/README.md`. The
authoritative links are the TI LMR51430 datasheet
(`https://www.ti.com/lit/ds/symlink/lmr51430.pdf`), the Murata product page
(`https://www.murata.com/en-us/products/productdetail.aspx?partno=GRM32ER71E226KE15%23`),
the Murata DC-bias FAQ
(`https://www.murata.com/en-us/support/faqs/capacitor/ceramiccapacitor/char/0005`),
the KEMET ceramic FAQ
(`https://www.kemet.com/en/us/capacitors/ceramic/ceramics-faq.html`), and the
Bourns SRP1265A datasheet
(`https://bourns.com/docs/product-datasheets/srp1265a.pdf?sfvrsn=4db37134_43`).
